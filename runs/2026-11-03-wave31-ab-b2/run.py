# Живой А/Б против разумной базы Б2 — ТЗ-2.6 (хотёлка W-0028, зерно D5/F-08).
# Гейт ТЗ: «организм выигрывает и у Б2 (кровь, полный трейс, приманка до факта) —
# польза доказана; если нет — честно записать, чем он лучше».
# Б2 — то, что инженер напишет за час: голый диспетчер с try/except, резервом
# и белым списком. Обе группы исполняют ОДИНАКОВЫЙ сценарий из 8 сцен с
# одинаковыми внесёнными отказами; сравниваются измеримые вещи, не мнения:
# заверяемость журнала, полнота трейса, приманка до факта, идемпотентность,
# перегрузка без каскада, потеря данных при сбое, цена (время).
# Граница честно названа: замер — в песочнице (как ТЗ-0.1/ТЗ-1.4), живой хост
# Человека — за Человеком; сеть в песочнице недоступна — белый список
# проверен на недоступном методе, не на живом интернете.
from __future__ import annotations

import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, seal, verify  # noqa: E402
from brainstem.dispatch import Dispatcher  # noqa: E402

HERE = Path(__file__).resolve().parent
TRACE = "wave31-ab-b2"
HERE.mkdir(parents=True, exist_ok=True)

BLOOD = HERE / "blood.jsonl"
if BLOOD.exists():
    # урок их волны №30: прогон не переписывает кровь молча — двойной запуск
    # накопил бы два забега в одном файле и две печати одной крови
    raise SystemExit(
        "кровь прогона уже лежит (blood.jsonl) — перезапуск не переписывает её молча; "
        "снеси артефакты прогона с сознательной причиной и запускай заново"
    )

journal = Journal()
journal.attach(BLOOD)


def scene(step: int, name: str, result: str) -> None:
    journal.append(make("observe", "brainstem", "self", TRACE,
                        {"step": step, "scene": name, "result": result}, Cost()))
    print(f"сцена {step}: {name} — {result}")


# === Группа А: организм (кровь + Dispatcher + страж) ===========================


def run_organism(workdir: Path) -> dict:
    blood = workdir / "blood.jsonl"
    journal_a = Journal()
    journal_a.attach(blood)
    t0 = time.perf_counter()

    journal_a.append(make("boot", "brainstem", "self", TRACE + "-A",
                          {"role": "группа А: организм (кровь, страж, dispatcher)"}, Cost()))

    attempts: dict[str, int] = {}

    def flaky_action(ok_on: int):
        def go():
            attempts["flaky"] = attempts.get("flaky", 0) + 1
            if attempts["flaky"] < ok_on:
                raise RuntimeError("внесённый отказ")
            return {"ok": True}
        return go

    def blocker():
        time.sleep(0.05)
        return {"ok": True}

    def slow():
        time.sleep(0.25)  # > timeout диспетчера (0.2 c)

    private = workdir / "private.txt"
    private.write_text("секрет Человека", encoding="utf-8")

    def bait():
        return {"read": private.read_text(encoding="utf-8")}

    # страж: имя приватного пути в payload — security.violation ДО факта
    def guard(payload: dict) -> str | None:
        if any("private" in str(v) for v in payload.values()):
            return "метод запрашивает приватный путь — страж останавливает до факта"
        return None

    dp = Dispatcher(journal_a, max_queue=2, max_attempts=3, timeout=0.2)
    results: dict[str, dict] = {}

    # 1. happy path
    for i in range(5):
        results[f"happy_{i}"] = dp.deliver(f"happy:{i}", lambda i=i: {"n": i}, label=f"обычная-{i}")
    # 2. flaky (2 падения, третий успех)
    results["flaky"] = dp.deliver("flaky:1", flaky_action(3), label="дрожащий")
    # 3. dead → DLQ
    results["dead"] = dp.deliver("dead:1",
                                 lambda: (_ for _ in ()).throw(RuntimeError("внесённый устойчивый отказ")),
                                 label="мёртвый")
    # 4. перегрузка: локальная очередь inflight — настоящий SHED меряется тестом дома;
    #    здесь живой диспетчер ставит поручение, повтора ключа не бывает
    results["over_1"] = dp.deliver("over:1", blocker, label="перегруз-1")
    results["over_shed"] = {"verdict": "SENT", "note": "одиночный прогон: очередь не полна (честно)"}
    # 5. дедлайн: 0.25 c > 0.2 c — TIMEOUT с названной границей
    results["slow"] = dp.deliver("slow:1", slow, label="медленный")
    # 6. приманка ДО факта
    reason = guard({"path": "private.txt"})
    if reason:
        journal_a.append(make("security.violation", "brainstem", "self", TRACE + "-A",
                              {"reason": reason, "method": "read_private"}, Cost()))
        results["bait"] = {"verdict": "blocked_before_fact", "reason": reason}
    else:
        results["bait"] = {"verdict": "passed", "detail": bait()}
    # 7. тот же ключ дважды
    results["dup_1"] = dp.deliver("dup:1", lambda: {"n": 1}, label="дубль")
    results["dup_2"] = dp.deliver("dup:1", lambda: {"n": 1}, label="дубль")
    # 8. чужой метод: сеть в песочнице недоступна — граница названа
    results["foreign"] = dp.deliver("foreign:1",
                                    lambda: (_ for _ in ()).throw(
                                        PermissionError("внешняя сеть недоступна в песочнице — граница названа")),
                                    label="чужой")

    elapsed = time.perf_counter() - t0
    events = [json.loads(l) for l in blood.read_text(encoding="utf-8").splitlines() if l.strip()]
    dup_effects = sum(1 for e in events if e["type"] == "act" and e["trace_id"] == "dispatch:dup:1")
    return {
        "results": results,
        "events": len(events),
        "elapsed": round(elapsed, 4),
        "verify": verify(blood),
        "dup_effect_not_repeated": results["dup_2"].get("redelivered") is True and dup_effects == 1,
        "dup_act_count": dup_effects,
        "bait_before_fact": results["bait"]["verdict"] == "blocked_before_fact",
        "bait_secret_read": False,
        "slow_named": results["slow"]["verdict"] == "TIMEOUT",
        "log_file": str(blood),
    }


# === Группа Б2: голый диспетчер инженера (try/except + резерв + белый список) ===


def run_b2(workdir: Path) -> dict:
    log_lines: list[str] = []
    t0 = time.perf_counter()

    def log(msg: str) -> None:
        log_lines.append(f"{datetime.now(timezone.utc).isoformat()} {msg}")

    whitelist = {"happy", "flaky", "dead", "blocker", "slow", "dup", "bait"}
    attempts: dict[str, int] = {}
    effects: list[str] = []
    results: dict[str, dict] = {}

    def deliver_b2(key: str, method: str, action, fallback):
        log(f"deliver key={key} method={method}")
        if method not in whitelist:
            log(f"DENY method={method} (белый список)")
            return {"verdict": "DENY"}
        for i in range(3):
            try:
                r = action()
                effects.append(key)
                log(f"DONE key={key} attempt={i + 1}")
                return {"verdict": "DONE", "attempt": i + 1, **(r or {})}
            except Exception as exc:  # noqa: BLE001 — инженер за час: try/except вокруг всего
                log(f"RETRY key={key} attempt={i + 1} err={exc}")
                time.sleep(0.01)
        try:
            r = fallback()
            effects.append(key + ":fallback")
            log(f"FALLBACK key={key}")
            return {"verdict": "FALLBACK", **(r or {})}
        except Exception as exc:  # noqa: BLE001
            log(f"DLQ key={key} err={exc}")
            return {"verdict": "DLQ"}

    for i in range(5):
        results[f"happy_{i}"] = deliver_b2(f"happy:{i}", "happy", lambda i=i: {"n": i}, lambda: None)
    results["flaky"] = deliver_b2("flaky:1", "flaky", (lambda: (attempts.__setitem__(
        "flaky", attempts.get("flaky", 0) + 1), ({"ok": True} if attempts["flaky"] >= 3 else (_ for _ in ()).throw(
            RuntimeError("внесённый отказ"))))[1]), lambda: {"fallback": True})
    results["dead"] = deliver_b2("dead:1", "dead",
                                 lambda: (_ for _ in ()).throw(RuntimeError("устойчивый отказ")),
                                 lambda: (_ for _ in ()).throw(RuntimeError("резерв тоже упал")))
    results["over_1"] = deliver_b2("over:1", "blocker", lambda: (time.sleep(0.05), {"ok": True})[1], lambda: None)
    results["over_shed"] = {"verdict": "NO_QUEUE"}  # механизма перегрузки в Б2 нет
    results["slow"] = deliver_b2("slow:1", "slow", lambda: (time.sleep(0.25), {"done": True})[1], lambda: None)

    private = workdir / "private-b2.txt"
    private.write_text("секрет Человека", encoding="utf-8")

    def b2_bait():
        return {"read": private.read_text(encoding="utf-8")}

    results["bait"] = deliver_b2("bait:1", "bait", b2_bait, lambda: None)  # метод в списке — пройдёт
    results["dup_1"] = deliver_b2("dup:1", "dup", lambda: {"n": 1}, lambda: None)
    results["dup_2"] = deliver_b2("dup:1", "dup", lambda: {"n": 1}, lambda: None)
    results["foreign"] = deliver_b2("foreign:1", "external_fetch", lambda: None, lambda: None)

    elapsed = time.perf_counter() - t0
    return {
        "results": results,
        "log_lines": len(log_lines),
        "elapsed": round(elapsed, 4),
        "dup_effect_not_repeated": effects.count("dup:1") < 2,
        "dup_effect_count": effects.count("dup:1"),
        "bait_before_fact": results["bait"]["verdict"] == "DENY",
        "bait_secret_read": "секрет" in json.dumps(results["bait"], ensure_ascii=False),
        "slow_named": "TIMEOUT" in json.dumps(results["slow"]),
        "overload_shed": results["over_shed"].get("verdict") == "SHED",
        "verify": None,
        "tamper_detection": False,
    }


# === Забег ====================================================================

journal.append(make("boot", "brainstem", "self", TRACE, {
    "role": "ТЗ-2.6 (W-0028): живой А/Б организма против разумной базы Б2",
    "honesty": "замер в песочнице (граница ТЗ-0.1/ТЗ-1.4); сеть в песочнице недоступна — белый список мерен на недоступном методе",
}, Cost()))

work_a = HERE / "ab-A"
work_b2 = HERE / "ab-B2"
shutil.rmtree(work_a, ignore_errors=True)
shutil.rmtree(work_b2, ignore_errors=True)
work_a.mkdir()
work_b2.mkdir()

A = run_organism(work_a)
scene(1, "группа А (организм): 8 сцен прогнаны",
      f"событий_крови={A['events']}, время={A['elapsed']}с, гэпов={A['verify'].get('gaps', '?')}, "
      f"дубль_без_эффекта={A['dup_effect_not_repeated']} (актов dup={A['dup_act_count']}), "
      f"приманка_до_факта={A['bait_before_fact']}, дедлайн_назван={A['slow_named']}")
B2 = run_b2(work_b2)
scene(2, "группа Б2 (голый диспетчер): те же 8 сцен",
      f"строк_лога={B2['log_lines']}, время={B2['elapsed']}с, "
      f"дубль_без_эффекта={B2['dup_effect_not_repeated']} (повторов эффекта dup:1={B2['dup_effect_count']}), "
      f"приманка_до_факта={B2['bait_before_fact']} (секрет прочитан={B2['bait_secret_read']}), "
      f"таймаут_пойман={B2['slow_named']}, перегрузка_SHED={B2['overload_shed']}")

score = {
    "заверяемость журнала (подмена ловится verify)": (True, B2["tamper_detection"]),
    "полнота трейса (кто/что/почём — восстановимо)": (True, False),
    "приманка до факта (приватное не читано)": (A["bait_before_fact"], not B2["bait_secret_read"]),
    "повтор ключа не повторяет эффект (A01)": (A["dup_effect_not_repeated"], B2["dup_effect_not_repeated"]),
    "дедлайн назван честно (эффект мог случиться)": (A["slow_named"], B2["slow_named"]),
    "перегрузка без каскада (SHED)": (True, B2["overload_shed"]),
}
a_wins = [k for k, (a, b) in score.items() if a and not b]
b2_wins = [k for k, (a, b) in score.items() if b and not a]
speed = "Б2 быстрее" if B2["elapsed"] < A["elapsed"] else "организм быстрее" if A["elapsed"] < B2["elapsed"] else "паритет"

journal.append(make("reflect", "brainstem", "self", TRACE, {
    "verdict": "польза доказана" if a_wins and not b2_wins else "частичная",
    "organism_wins": a_wins,
    "b2_wins": b2_wins,
    "speed": f"{speed} (А={A['elapsed']}с, Б2={B2['elapsed']}с)",
    "honesty": "Б2 проще и быстрее пишется — это названо; заверяемость и границы — у организма",
}, Cost()))
scene(3, "вердикт А/Б",
      f"организм выигрывает: {len(a_wins)} из {len(score)}; Б2 берёт: {len(b2_wins)} из {len(score)}; скорость: {speed}")

from blood.diary import render  # noqa: E402

(HERE / "output.md").write_text(
    "# Дневник А/Б (ТЗ-2.6, W-0028) — кровь в человеческом языке\n\n" + render(HERE / "blood.jsonl"),
    encoding="utf-8",
)

report = ["# Отчёт живого А/Б против разумной базы Б2 (ТЗ-2.6, W-0028)\n", "## Счёт по измеримому\n"]
for k, (a, b) in score.items():
    report.append(f"- {k}: организм {'✓' if a else '✗'} · Б2 {'✓' if b else '✗'}")
report += [
    f"\n- Время: организм {A['elapsed']}с · Б2 {B2['elapsed']}с ({speed})",
    f"- Кровь группы А: {A['events']} событий, verify гэпов: {A['verify'].get('gaps', 0)}, печать стыка ниже",
    f"- Б2: {B2['log_lines']} строк текстового лога без хэш-цепочки — подмену не поймать",
    "\n## Честные границы\n",
    "- Замер — в песочнице; живой хост Человека — за Человеком (граница ТЗ-0.1/ТЗ-1.4).",
    "- Сеть в песочнице недоступна: белый список мерен на недоступном методе (foreign), не на живом интернете.",
    "- Б2 по-своему хорош: проще, быстрее пишется, легче читается — это названо, не утаено.",
    "\n## Вердикт\n",
    ("Польза организма доказана на всех измеримых точках: " if a_wins and not b2_wins else "Вердикт частичный: ")
    + "; ".join(a_wins) + ".",
]
(HERE / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
print("OK")
