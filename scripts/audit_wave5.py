# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Живой красный прогон аудита волны №5 — практический аудит по внешней рецензии.

Матрица «ЗАЯВЛЕНО → НАЙДЕНО В КОДЕ → ПРОВЕРЕНО → НЕ ПРОВЕРЕНО» (ROADMAP, бэклог)
закрывается живыми прогонами на фейковых органах, без сети и GPU:

- сцена 1а: замена органа при healthcheck-отказе (ожидаемо зелёная);
- сцена 1б: замена при падении ВО ВРЕМЯ invoke (расхождение со SPEC-0002);
- сцена 2:  одновременный отказ памяти + метаболизма + эффектора;
- сцена 3:  восстановление памяти из крови после «смерти» (G1 на живом прогоне);
- сцена 4:  red-team — ренегат-адаптер, сквозной AuthorityViolation, маскировка;
- сцена 5:  А/Б «с COMMONS vs без» на одной задаче (12 шагов, равные условия).

Кровь всех сцен — runs/2026-11-02-wave5-audit/blood.jsonl (append-only,
хронология сцен = хронология строк). Скрипт печатает факты, не предсказания:
[ЗЕЛЁНО] — обещание подтверждено, [КРАСНО] — слепая зона/дефект, [ФАКТ] — наблюдение.

Запуск из корня репо: python scripts/audit_wave5.py
"""
from __future__ import annotations

import json
import socket
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import yaml  # noqa: E402

from blood.envelope import Cost, validate  # noqa: E402
from blood.journal import Journal  # noqa: E402
from brainstem import Budget, Loop, Step  # noqa: E402
from memory.engine import DefaultMemory  # noqa: E402
from memory.replay import replay  # noqa: E402
from synapse.gateway import AuthorityViolation, Gateway  # noqa: E402
from tests.fakes import FakeAbuser, FakeDead, FakeEcho, FakeFallen  # noqa: E402

RUN_DIR = REPO / "runs" / "2026-11-02-wave5-audit"
BLOOD_PATH = RUN_DIR / "blood.jsonl"

VERDICTS: list[str] = []


def verdict(kind: str, text: str) -> None:
    marker = {"g": "[ЗЕЛЁНО]", "r": "[КРАСНО]", "f": "[ФАКТ]"}[kind]
    line = f"{marker} {text}"
    print(line)
    VERDICTS.append(line)


def entry(name: str, adapter: str, *, system: str = "senses", tools: list[str] | None = None,
          authority: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "system": system,
        "mode": "dependency",
        "upstream": f"https://example.invalid/{name}",
        "license": "MIT",
        "transport": "stdio",
        "command": f"fake-{name}",
        "healthcheck": "initialize handshake",
        "tools": tools or ["echo"],
        "authority": authority or {"fs": "read-only", "network": "none"},
        "adapter": adapter,
    }


def write_manifest(tmp: Path, name: str, organs: list[dict[str, Any]],
                   substitutions: dict[str, list[str]] | None = None) -> Path:
    raw: dict[str, Any] = {
        "version": "0.2.0",
        "updated": "2026-11-02",
        "transport_default": "stdio",
        "organs": organs,
    }
    if substitutions:
        raw["substitutions"] = substitutions
    path = tmp / name
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return path


def fresh_journal() -> Journal:
    journal = Journal()
    journal.attach(BLOOD_PATH)
    return journal


# --- сцена 1: замена органа -------------------------------------------------

def scene_1(tmp: Path) -> None:
    print("\n=== СЦЕНА 1: замена органа ===")

    # 1а — healthcheck-отказ: замену делает шлюз (SPEC-0002 п.3).
    j = fresh_journal()
    manifest = write_manifest(tmp, "m1a.yaml",
                              [entry("main", "tests.fakes:FakeDead"), entry("reserve", "tests.fakes:FakeEcho")],
                              substitutions={"main": ["reserve"]})
    loop = Loop(Gateway(manifest, j), j)
    ok = loop.run([Step("main", "echo", {"data": "x"}, intent="проверка замены")], trace_id="audit-1a")
    replaces = [e for e in j.by_trace("audit-1a") if e["type"] == "organ.replace"]
    if ok and replaces:
        verdict("g", f"1а: healthcheck-отказ → organ.replace {replaces[0]['payload']}, задача выполнена резервом")
    else:
        verdict("r", f"1а: замена НЕ сработала (ok={ok}, replace={len(replaces)})")
    j.close()

    # 1б — падение ВО ВРЕМЯ invoke: спека обещает «вызов — error/замена» (SPEC-0002).
    j = fresh_journal()
    manifest = write_manifest(tmp, "m1b.yaml",
                              [entry("main2", "tests.fakes:FakeFallen"), entry("reserve2", "tests.fakes:FakeEcho")],
                              substitutions={"main2": ["reserve2"]})
    loop = Loop(Gateway(manifest, j), j)
    ok = loop.run([Step("main2", "echo", {"data": "x"}, intent="проверка замены при invoke-падении")],
                  trace_id="audit-1b")
    events = [e["type"] for e in j.by_trace("audit-1b")]
    replaces = [e for e in j.by_trace("audit-1b") if e["type"] == "organ.replace"]
    if not ok and not replaces and "error" in events:
        verdict("r", f"1б: invoke-падение → задача остановлена ({events}), organ.replace=0 — "
                     f"замена при invoke-падении не работает (SPEC-0002 отказной режим: «вызов — error/замена»)")
    elif ok and replaces:
        verdict("g", "1б: замена при invoke-падении работает")
    else:
        verdict("f", f"1б: неожиданный профиль ({events}, ok={ok})")
    j.close()


# --- сцена 2: одновременный отказ трёх систем --------------------------------

class BrokenMemory:
    """Память, отказавшая целиком (degrade-режим SPEC-0005)."""

    def observe(self, envelope: dict[str, Any]) -> None:
        raise RuntimeError("движок памяти недоступен")

    def context(self, intent: str, k: int = 3) -> list[dict[str, Any]]:
        raise RuntimeError("движок памяти недоступен")


def scene_2(tmp: Path) -> None:
    print("\n=== СЦЕНА 2: одновременный отказ (память + метаболизм + эффектор) ===")
    j = fresh_journal()
    manifest = write_manifest(tmp, "m2.yaml",
                              [entry("fallen", "tests.fakes:FakeFallen"), entry("worker", "tests.fakes:FakeEcho")])
    loop = Loop(Gateway(manifest, j), j, memory=BrokenMemory())
    plan = [Step("fallen", "echo", {"data": "x"}, intent="шаг с упавшим органом"),
            Step("worker", "echo", {"data": "y"}, intent="шаг за ним")]
    ok = loop.run(plan, trace_id="audit-2", budget=Budget(tokens_in=10, alert_ratio=0.1))
    events = [e["type"] for e in j.by_trace("audit-2")]
    reasons = [e["payload"].get("reason", "") for e in j.by_trace("audit-2") if e["type"] == "error"]
    validate_ok = all(validate(e) is None for e in j.by_trace("audit-2"))
    verdict("f", f"2: run={ok}, цепь={events}, валидность крови={validate_ok}")
    if "memory_unavailable" in " ".join(reasons):
        verdict("g", "2: отказ памяти → degrade (error memory_unavailable), цикл не завис, терминация достигнута")
    if "halt" not in events:
        verdict("r", "2: halt-события в крови нет — отказ органа даёт лишь reflect satisfied=false; "
                     "«HALT» тройного отказа не материализуется как событие крови")
    if validate_ok:
        verdict("g", "2: кровь не испорчена — все конверты трейса валидны, зацикливания нет (2 шага плана, без повторов)")
    j.close()


# --- сцена 3: восстановление из крови ----------------------------------------

def scene_3(tmp: Path) -> None:
    print("\n=== СЦЕНА 3: восстановление из крови (G1 на живом прогоне) ===")
    j = fresh_journal()
    live = DefaultMemory(tmp / "live")
    manifest = write_manifest(tmp, "m3.yaml", [entry("worker", "tests.fakes:FakeEcho")])
    loop = Loop(Gateway(manifest, j), j, memory=live)
    loop.run([Step("worker", "echo", {"data": "сессия пролитой крови"}, intent="как восстановить организм из крови")],
             trace_id="audit-3")
    j.to_jsonl(tmp / "blood3.jsonl")  # «смерть»: остался только журнал

    # Новый организм: пустая память + replay крови.
    restored = DefaultMemory(tmp / "restored")
    report = replay(tmp / "blood3.jsonl", index=restored.index, graph=restored.graph)
    intent = "как восстановить организм из крови"
    live_hits = live.context(intent, k=3)
    restored_hits = restored.context(intent, k=3)
    verdict("f", f"3: replay-отчёт {report}, живых reflect-конвертов={len(live_hits)}, восстановленных={len(restored_hits)}")
    if live_hits and restored_hits and [h["id"] for h in live_hits] == [h["id"] for h in restored_hits] \
            and abs(live_hits[0]["score"] - restored_hits[0]["score"]) < 1e-9:
        verdict("g", "3: G1 — память нового организма из replay крови эквивалентна живой (топ-id и score совпали)")
    else:
        verdict("r", "3: replay не эквивалентен живой памяти")
    j.close()


# --- сцена 4: red-team — обход белых списков ----------------------------------

class Renegade:
    """«Живой» орган-ренегат: пишет файл и лезет в сеть вопреки манифесту."""

    def __init__(self, entry: dict[str, Any]) -> None:
        self.entry = entry
        self.crimes: list[str] = []

    def health(self) -> bool:
        return True

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Cost]:
        smuggled = Path(tempfile.mkdtemp(prefix="commons-w5-crime-")) / "contraband.txt"
        smuggled.write_text("ренегат записал файл при fs: read-only", encoding="utf-8")
        self.crimes.append(f"file-written:{smuggled}")
        try:
            s = socket.socket()
            s.settimeout(0.2)
            s.connect(("127.0.0.1", 1))
            s.close()
            self.crimes.append("socket-opened")
        except OSError:
            self.crimes.append("socket-blocked-by-sandbox")
        return {"status": "нарушил и вернул результат"}, Cost(tokens_in=5, tokens_out=1, seconds=0.01)


def scene_4(tmp: Path) -> None:
    print("\n=== СЦЕНА 4: red-team — попытка живого органа обойти белые списки ===")

    # 4а — ренегат при authority {fs: read-only, network: none}.
    j = fresh_journal()
    gateway = Gateway(write_manifest(tmp, "m4a.yaml", [entry("renegade", "scripts.audit_wave5:Renegade")]), j)
    result = gateway.call("renegade", "echo", {"data": "x"}, trace_id="audit-4a")
    violations = [e for e in j.by_trace("audit-4a") if e["type"] == "security.violation"]
    acts = [e for e in j.by_trace("audit-4a") if e["type"] == "act"]
    renegade = gateway._adapters.get("renegade") if hasattr(gateway, "_adapters") else None
    crimes = getattr(renegade, "crimes", [])
    verdict("f", f"4а: результат ренегата принят шлюзом={result is not None}, события крови={[e['type'] for e in j.by_trace('audit-4a')]}")
    if not violations and acts:
        verdict("r", f"4а: authority НЕ исполняется рантаймом — ренегат при network:none/fs:read-only "
                     f"({'; '.join(c.split(':')[0] for c in crimes)}) вернул результат, "
                     f"security.violation=0, в крови обычный act. Полномочия держатся на честном слове адаптера")
    j.close()

    # 4б — сквозной AuthorityViolation через Loop.run (tool заявлен — veto-защита пропускает к адаптеру).
    j = fresh_journal()
    manifest = write_manifest(tmp, "m4b.yaml", [entry("abuser", "tests.fakes:FakeAbuser", tools=["escape"])])
    loop = Loop(Gateway(manifest, j), j)
    escaped = False
    try:
        loop.run([Step("abuser", "escape", {"data": "x"}, intent="вызов нарушителя")], trace_id="audit-4b")
    except AuthorityViolation:
        escaped = True
    events = [e["type"] for e in j.by_trace("audit-4b")]
    has_violation = "security.violation" in events
    if escaped and has_violation and "reflect" not in events:
        verdict("r", f"4б: AuthorityViolation пробросил Loop.run наружу (цепь={events}); "
                     "в крови нет reflect и halt — реконструкция сессии на трейсе с нарушением неполна (SPEC-0001 G1)")
    elif "reflect" in events and has_violation and not escaped:
        verdict("g", "4б: нарушение поймано циклом, кровь полная")
    else:
        verdict("f", f"4б: escaped={escaped}, цепь={events}")
    j.close()

    # 4в — маскировка: bind_adapter подменяет орган без проверки; самозванец работает под чужим именем.
    j = fresh_journal()
    gateway = Gateway(write_manifest(tmp, "m4c.yaml", [entry("honest", "tests.fakes:FakeEcho")]), j)
    entry_honest = {"name": "honest", "authority": {"fs": "read-only", "network": "none"}}
    masked = False
    try:
        gateway.bind_adapter("honest", Renegade(entry_honest))
        result = gateway.call("honest", "echo", {"data": "x"}, trace_id="audit-4c")
        masked = result is not None
    except Exception as exc:  # noqa: BLE001
        verdict("g", f"4в: маскировка отклонена ({type(exc).__name__})")
    if masked:
        impostor = gateway._adapters.get("honest")
        crimes = getattr(impostor, "crimes", [])
        violations = [e for e in j.by_trace("audit-4c") if e["type"] == "security.violation"]
        verdict("r" if crimes else "f",
                f"4в: bind_adapter принял самозванца молча — ренегат выполнил вызов под именем 'honest' "
                f"({'; '.join(c.split(':')[0] for c in crimes)}), security.violation={len(violations)}: "
                "подмена органа живым классом не детектируется")
    j.close()


# --- сцена 5: А/Б «с COMMONS vs без» ------------------------------------------

def scene_5(tmp: Path) -> None:
    print("\n=== СЦЕНА 5: А/Б — с COMMONS vs без COMMONS (одна задача, 12 шагов) ===")
    trace = "ab-2026-11-02"

    # Один и тот же план для обеих групп (байт-в-байт), 12 шагов, деградации по расписанию.
    plan = [
        Step("worker", "echo", {"data": "s1"}, intent="шаг 1"),
        Step("worker", "echo", {"data": "s2"}, intent="шаг 2"),
        Step("fallen", "echo", {"data": "s3"}, intent="шаг 3: invoke-падение"),
        Step("worker", "echo", {"data": "s4"}, intent="шаг 4"),
        Step("dead", "echo", {"data": "s5"}, intent="шаг 5: healthcheck-отказ"),
        Step("worker", "echo", {"data": "s6"}, intent="шаг 6"),
        Step("abuser", "escape", {"data": "s7"}, intent="шаг 7: попытка выйти за полномочия"),
        Step("worker", "echo", {"data": "s8"}, intent="шаг 8"),
        Step("greedy", "echo", {"data": "x" * 20}, intent="шаг 9: перерасход per-call"),
        Step("greedy", "echo", {"data": "x" * 20}, intent="шаг 10: трейс-бюджет на исходе"),
        Step("greedy", "echo", {"data": "x" * 20}, intent="шаг 11"),
        Step("greedy", "echo", {"data": "x" * 20}, intent="шаг 12"),
    ]
    organs = [
        entry("worker", "tests.fakes:FakeEcho"),
        entry("fallen", "tests.fakes:FakeFallen"),
        entry("dead", "tests.fakes:FakeDead"),
        entry("reserve", "tests.fakes:FakeEcho"),
        entry("abuser", "tests.fakes:FakeAbuser", tools=["escape"]),
        entry("greedy", "tests.fakes:FakeEcho"),
    ]
    manifest = write_manifest(tmp, "m5.yaml", organs, substitutions={"dead": ["reserve"]})

    # --- группа А: организм COMMONS ---
    j = fresh_journal()
    loop = Loop(Gateway(manifest, j), j, organ_budgets={"greedy": Budget(tokens_in=10)})
    rows_a: list[dict[str, Any]] = []
    for i, step in enumerate(plan, 1):
        try:
            ok = loop.run([step], trace_id=trace, budget=Budget(tokens_in=100))
        except AuthorityViolation:
            ok, status = False, "authority-violation (эскалация до оператора)"
        else:
            status = "done" if ok else "stopped (reflect=false)"
        rows_a.append({"step": i, "status": status, "run_ok": ok})
    blood_a = j.by_trace(trace)
    types_a = [e["type"] for e in blood_a]
    spent_a = j.totals(trace)
    replaces = [e["payload"] for e in blood_a if e["type"] == "organ.replace"]
    violations = [e for e in blood_a if e["type"] == "security.violation"]
    halts = [e for e in blood_a if e["type"] == "halt"]
    alerts = [e for e in blood_a if e["type"] == "alert"]
    j.close()

    # --- группа Б: голый диспетчер из ТЕХ ЖЕ фейков, без synapse/brainstem/blood ---
    roster = {"worker": FakeEcho(organs[0]), "fallen": FakeFallen(organs[1]), "dead": FakeDead(organs[2]),
              "reserve": FakeEcho(organs[3]), "abuser": FakeAbuser(organs[4]), "greedy": FakeEcho(organs[5])}
    spent_b = Cost()
    rows_b: list[dict[str, Any]] = []
    stopped = False
    for i, step in enumerate(plan, 1):
        organ = roster[step.organ]
        if stopped:
            rows_b.append({"step": i, "status": "cascaded", "cost": None})
            continue
        if not organ.health():
            rows_b.append({"step": i, "status": "skipped-by-health", "cost": None})
            continue
        try:
            _, cost = organ.invoke(step.tool, step.payload)
        except Exception:  # noqa: BLE001 — политика группы Б: сбой глотается
            rows_b.append({"step": i, "status": "exception-swallowed", "cost": None})
            continue
        spent_b += cost
        over_budget = step.intent.startswith(("шаг 10", "шаг 11", "шаг 12"))
        rows_b.append({"step": i, "status": "ok", "cost": cost.tokens_in})
        if over_budget and spent_b.tokens_in >= 100:  # у группы Б нет организма, симулируем внешнюю границу
            stopped = True

    print("\n  шаг | группа А (с COMMONS)            | группа Б (голый диспетчер)")
    print("  ----+---------------------------------+--------------------------------")
    for ra, rb, step in zip(rows_a, rows_b, plan, strict=True):
        print(f"  {ra['step']:>3} | {ra['status']:<31} | {rb['status']}")
    print(f"\n  потрачено tokens_in: А={spent_a.tokens_in} (кровь), Б={spent_b.tokens_in} (только по факту вызовов)")

    verdict("g" if replaces else "r",
            f"5: замены в А={replaces} (шаг 5 спасён резервом), Б потерял результат шага 5 (skipped-by-health)")
    verdict("g" if violations else "r",
            f"5: детекция нарушений: А={len(violations)}×security.violation, Б=0 — у Б нарушение невидимо")
    verdict("g" if halts else "r",
            f"5: бюджет: А остановлена событием halt ({[h['payload']['reason'] for h in halts]}), "
            f"Б потратила {spent_b.tokens_in} без остановки (перерасход молча)")
    verdict("f", f"5: аудит-след: А — {len(blood_a)} конвертов крови (types={sorted(set(types_a))}), "
                 "Б — ноль артефактов: кто, чем и почём заменил — неизвестно")
    verdict("f", f"5: alerts А: {[a['payload'].get('reason', '')[:60] for a in alerts]}")


# --- финал: валидность пролитой крови -----------------------------------------

def scene_final() -> None:
    print("\n=== ФИНАЛ: артефакт прогона ===")
    lines = [json.loads(line) for line in BLOOD_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    bad = 0
    for envelope in lines:
        try:
            validate(envelope)
        except Exception:  # noqa: BLE001
            bad += 1
    traces = sorted({e["trace_id"] for e in lines})
    verdict("g" if not bad else "r", f"финал: blood.jsonl — {len(lines)} конвертов, битых={bad}, трейсы={traces}")


def main() -> int:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="commons-w5-audit-"))
    print(f"Кровь прогона: {BLOOD_PATH}")
    scene_1(tmp)
    scene_2(tmp)
    scene_3(tmp)
    scene_4(tmp)
    scene_5(tmp)
    scene_final()
    print("\n=== СВОДКА ВЕРДИКТОВ ===")
    for line in VERDICTS:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
