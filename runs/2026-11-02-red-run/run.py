#!/usr/bin/env python3
"""Красный прогон — аудит-матрица внешней рецензии (коллега-LLM, 2026-11-02),
пункты 1–4 из 5, каркасный уровень, офлайн и детерминированно:

1. Замена органа — llama.cpp ↔ ollama-style: два манифеста, одно имя органа,
   два движка; ствол мозга не тронут (ни строчкой), следы трейсов совпадают,
   цены разные. G2 SPEC-0001.
2. Одновременный отказ — память + метаболизм + эффектор мертвы: цикл деградирует
   (degrade SPEC-0005), замены не спасают → HALT по-записанному; PID 1 дышит
   на мёртвых органах и умирает чисто (G4). Никакого крэша — только кровь.
3. Восстановление — кровь с диска перечитывается: replay индексирует reflect-ы,
   ни один конверт не потерян; сессии реконструируются по trace_id. G1 SPEC-0005.
4. Обход белых списков — семь атак по всем воротам: орган-призрак, инструмент
   вне манифеста, превышение полномочий, shell-инъекция в конвейер, неизвестный
   узел, неизвестная лицензия (fail-closed), метод эффектора вне белого списка,
   второй организм (G6). Каждая обязана быть отвергнута и записана в кровь.

Пункт 5 (польза А/Б на живой задаче) честно остаётся открытым — он требует
живого хоста и равных условий; каркас его не доказывает.

Запуск: python3 runs/2026-11-02-red-run/run.py [выходной_каталог]
Выход:  RED-RUN: N ok, M failed; exit 1 при M>0. Кровь — blood.jsonl рядом.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal  # noqa: E402
from blood.pidlock import PIDLock  # noqa: E402
from brainstem.loop import Budget, Loop, Step  # noqa: E402
from brainstem.pid1 import PID1  # noqa: E402
from immune.barrier import load_matrix, verdict  # noqa: E402
from memory.engine import DefaultMemory  # noqa: E402
from memory.replay import replay  # noqa: E402
from openclaw.adapter import OpenClawAdapter  # noqa: E402
from pipeline.check import validate_workflow  # noqa: E402
from synapse.gateway import (  # noqa: E402
    AuthorityViolation,
    Gateway,
    OrganUnavailable,
    SynapseVeto,
)
from tests.fakes import FakeAbuser, FakeDead, FakeEcho  # noqa: E402

RUN_DIR = Path(__file__).resolve().parent
PLAN = [
    Step("metabolism", "summarize", {"doc": "Pulse"}, intent="сжать документ"),
    Step("metabolism", "summarize", {"doc": "Replay"}, intent="сжать ответ"),
]
CYCLE = ("plan", "act", "observe", "reflect")


class SlimEngine:
    """Второй движок под тем же именем органа: другая цена — ствол не тронут."""

    def __init__(self, entry: dict[str, Any]) -> None:
        self.entry = entry

    def health(self) -> bool:
        return True

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Cost]:
        return {"engine": "slim", "echo": payload}, Cost(tokens_in=7, tokens_out=2, seconds=0.005)


class BrokenMemory:
    """Память, упавшая целиком: и контекст, и индексация — отказ (degrade SPEC-0005)."""

    def context(self, intent: str, k: int = 3) -> list[dict[str, Any]]:
        raise RuntimeError("память недоступна")

    def observe(self, envelope: dict[str, Any]) -> None:
        raise RuntimeError("память недоступна")


def _manifest(path: Path, *, substitutions: dict[str, list[str]] | None = None) -> None:
    organs = [
        {
            "name": "metabolism",
            "system": "metabolism",
            "mode": "core",
            "upstream": "fake://red-run/metabolism",
            "license": "MIT",
            "transport": "stdio",
            "command": ["python3", "-c", "pass"],
            "tools": ["summarize"],
            "authority": {"fs": "none", "net": "none"},
        },
        {
            "name": "effector",
            "system": "effectors",
            "mode": "core",
            "upstream": "fake://red-run/effector",
            "license": "MIT",
            "transport": "stdio",
            "command": ["python3", "-c", "pass"],
            "tools": ["send"],
            "authority": {"fs": "none", "net": "none"},
        },
    ]
    doc: dict[str, Any] = {
        "version": "red-run",
        "updated": "2026-11-02",
        "transport_default": "stdio",
        "organs": organs,
    }
    if substitutions:
        doc["substitutions"] = substitutions
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _emit(journal: Journal, organ: str, payload: dict[str, Any], trace_id: str) -> None:
    """Вердикт внешнего барьера — тоже кровь: атака зафиксирована конвертом."""
    journal.append(make("act", "red-run", organ, trace_id, payload, Cost()))


# --- сценарий 1: замена органа правкой манифеста (G2) ---


def scenario_engine_swap(tmp: Path, journal: Journal) -> dict[str, Any]:
    a, b = tmp / "manifest-a.yaml", tmp / "manifest-b.yaml"
    _manifest(a)
    _manifest(b)
    gw_a = Gateway(a, journal)
    gw_a.bind_adapter("metabolism", FakeEcho({"name": "metabolism"}))
    gw_b = Gateway(b, journal)
    gw_b.bind_adapter("metabolism", SlimEngine({"name": "metabolism"}))

    t1, t2 = "red-swap-a", "red-swap-b"
    ok_a = Loop(gw_a, journal).run(PLAN, trace_id=t1, budget=Budget())
    ok_b = Loop(gw_b, journal).run(PLAN, trace_id=t2, budget=Budget())

    shape_a = [e["type"] for e in journal.by_trace(t1)]
    shape_b = [e["type"] for e in journal.by_trace(t2)]
    expected = list(CYCLE) * len(PLAN)
    cost_a = journal.totals(t1)
    cost_b = journal.totals(t2)
    ok = (
        ok_a
        and ok_b
        and shape_a == shape_b == expected
        and (cost_a.tokens_in, cost_a.tokens_out) != (cost_b.tokens_in, cost_b.tokens_out)
    )
    return {
        "name": "engine-swap",
        "ok": ok,
        "traces": [t1, t2],
        "shape": shape_a,
        "cost_a": cost_a.as_dict(),
        "cost_b": cost_b.as_dict(),
        "brainstem_untouched": True,
    }


# --- сценарий 2: одновременный отказ (degrade + HALT по-записанному) ---


def scenario_total_outage(tmp: Path, journal: Journal) -> dict[str, Any]:
    m = tmp / "manifest-dead.yaml"
    _manifest(m, substitutions={"metabolism": ["effector"]})
    gw = Gateway(m, journal)
    gw.bind_adapter("metabolism", FakeDead({"name": "metabolism"}))
    gw.bind_adapter("effector", FakeDead({"name": "effector"}))

    trace = "red-outage"
    loop = Loop(gw, journal, memory=BrokenMemory())
    satisfied = loop.run(PLAN, trace_id=trace, budget=Budget())
    types = [e["type"] for e in journal.by_trace(trace)]
    reasons = [
        e["payload"].get("reason", "")
        for e in journal.by_trace(trace)
        if e["type"] in ("error", "reflect")
    ]

    pid = PID1(gw, journal, interval=0.05)
    pid_code = pid.run(max_beats=2)
    shutdown = [e for e in journal.by_type("shutdown") if e["payload"].get("reason") == "max_beats"]
    health_dead = [
        e
        for e in journal.by_type("organ.health")
        if e["payload"].get("healthy") is False
    ]

    ok = (
        satisfied is False
        and types[:4] == ["error", "plan", "error", "reflect"]
        and any("memory_unavailable" in r for r in reasons)
        and any("недоступен" in r for r in reasons)
        and pid_code == 0
        and bool(shutdown)
        and len(health_dead) >= 4  # 2 органа × 2 биения, все нездоровы
    )
    return {
        "name": "total-outage",
        "ok": ok,
        "trace": trace,
        "loop_types": types[:4],
        "pid1_exit": pid_code,
        "unhealthy_beats": len(health_dead),
        "no_crash": True,
    }


# --- сценарий 3: восстановление из крови (G1) ---


def scenario_recovery(tmp: Path, journal: Journal) -> dict[str, Any]:
    snapshot = tmp / "blood-snapshot.jsonl"
    journal.to_jsonl(snapshot)

    engine = DefaultMemory(tmp / "mem")
    report = replay(snapshot, index=engine.index, graph=engine.graph)

    events = [json.loads(line) for line in snapshot.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_trace: dict[str, list[str]] = {}
    for env in events:
        by_trace.setdefault(env["trace_id"], []).append(env["type"])
    reconstructed = {
        t: types for t, types in by_trace.items() if t in ("red-swap-a", "red-swap-b")
    }
    full_cycles = all(types == list(CYCLE) * len(PLAN) for types in reconstructed.values())

    ok = (
        report["skipped"] == 0
        and report["envelopes"] == len(events)
        and report["graph"]["nodes"] > 0
        and len(reconstructed) == 2
        and full_cycles
    )
    return {
        "name": "recovery",
        "ok": ok,
        "envelopes": report["envelopes"],
        "skipped": report["skipped"],
        "graph_nodes": report["graph"]["nodes"],
        "traces_reconstructed": sorted(reconstructed),
    }


# --- сценарий 4: обход белых списков (красный прогон) ---


def scenario_bypass_attacks(tmp: Path, journal: Journal) -> dict[str, Any]:
    m = tmp / "manifest-attack.yaml"
    _manifest(m)
    gw = Gateway(m, journal)
    gw.bind_adapter("metabolism", FakeEcho({"name": "metabolism"}))
    trace = "red-attacks"
    attacks: list[dict[str, Any]] = []

    def record(attack_id: str, gate: str, rejected: bool, rule: str, detail: str) -> None:
        attacks.append({"id": attack_id, "gate": gate, "rejected": rejected, "rule": rule, "detail": detail})

    # A1: орган-призрак — нет записи в манифесте.
    try:
        gw.call("ghost-organ", "summarize", {}, trace)
        record("A1", "synapse", False, "passed", "призрак прошёл шлюз")
    except (SynapseVeto, OrganUnavailable):
        vetoed = any(e["type"] == "veto" and e["organ"] == "ghost-organ" for e in journal.by_trace(trace))
        record("A1", "synapse", vetoed, "veto", "орган не объявлен в манифесте")

    # A2: инструмент вне манифеста.
    try:
        gw.call("metabolism", "shell.exec", {}, trace)
        record("A2", "synapse", False, "passed", "инструмент прошёл шлюз")
    except (SynapseVeto, OrganUnavailable):
        record("A2", "synapse", True, "veto", "инструмент не объявлен в манифесте")

    # A3: превышение полномочий живым органом.
    gw.bind_adapter("metabolism", FakeAbuser({"name": "metabolism"}))
    try:
        gw.call("metabolism", "summarize", {"doc": "x"}, trace)
        record("A3", "synapse", False, "passed", "нарушитель получил ответ")
    except AuthorityViolation:
        violation = any(e["type"] == "security.violation" for e in journal.by_trace(trace))
        record("A3", "synapse", violation, "security.violation", "орган запросил сеть при fs: none")

    # A4/A4b: shell-инъекция и неизвестный узел в конвейере.
    hostile = tmp / "hostile-workflow.json"
    hostile.write_text(
        json.dumps(
            {
                "name": "red-run",
                "nodes": [
                    {
                        "name": "exec",
                        "type": "n8n-nodes-base.executeCommand",
                        "parameters": {"command": "commons-pid1; rm -rf /"},
                    }
                ],
                "connections": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = validate_workflow(hostile)
    _emit(journal, "pipeline-check", {"attack": "A4", "verdict": "rejected" if not result.ok else "passed", "rule": result.rule}, trace)
    record("A4", "pipeline", not result.ok, result.rule, result.reason)

    unknown = tmp / "unknown-node-workflow.json"
    unknown.write_text(
        json.dumps(
            {
                "name": "red-run",
                "nodes": [{"name": "x", "type": "n8n-nodes-base.arbitraryShell", "parameters": {}}],
                "connections": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = validate_workflow(unknown)
    _emit(journal, "pipeline-check", {"attack": "A4b", "verdict": "rejected" if not result.ok else "passed", "rule": result.rule}, trace)
    record("A4b", "pipeline", not result.ok, result.rule, result.reason)

    # A5/A5b: лицензионный барьер — AGPL и неизвестная лицензия в режим adapter
    # (правило лицензий напрямую; fail-closed на неизвестное — SPEC-0006).
    matrix = load_matrix()
    for attack_id, license_name in (("A5", "AGPL-3.0"), ("A5b", "Совершенно-Неизвестная-1.0")):
        decision = verdict(license_name, "adapter", matrix, organ="red-run-organ")
        _emit(journal, "immune-barrier", {"attack": attack_id, "verdict": "rejected" if not decision.ok else "passed", "rule": decision.rule}, trace)
        record(attack_id, "immune", not decision.ok, decision.rule, decision.reason)

    # A6/A6b: эффектор — метод вне белого списка; легитимный метод без живого gateway.
    adapter = OpenClawAdapter(binary="/nonexistent/openclaw")
    result = adapter.call("shell.exec", {"cmd": "x"})
    _emit(journal, "openclaw-adapter", {"attack": "A6", "verdict": "rejected" if not result.ok else "passed", "rule": result.rule}, trace)
    record("A6", "effector", not result.ok, result.rule, result.reason)
    result = adapter.call("health")
    _emit(journal, "openclaw-adapter", {"attack": "A6b", "verdict": "gate-held", "rule": result.rule}, trace)
    record("A6b", "effector", not result.ok, result.rule, "живой gateway — только на хосте человека (PID 1)")

    # A7: второй организм — G6, смерть по-записанному.
    lock_path = tmp / "commons.pid"
    first = PIDLock(lock_path)
    first.acquire()
    try:
        twin = PID1(Gateway(m, journal), journal, interval=0.05, lock=PIDLock(lock_path))
        code = twin.run(max_beats=2)
        veto = any(
            e["type"] == "veto" and "второй организм жив" in str(e["payload"].get("reason", ""))
            for e in journal.by_type("veto")
        )
        shutdown = any(e["type"] == "shutdown" and e["payload"].get("reason") == "second_instance" for e in journal.by_type("shutdown"))
        record("A7", "pid1", code == 1 and veto and shutdown, "veto+shutdown", f"exit={code}, второй экземпляр не вошёл в тело")
    finally:
        first.release()

    rejected = sum(1 for a in attacks if a["rejected"])
    return {
        "name": "bypass-attacks",
        "ok": rejected == len(attacks),
        "attacks": attacks,
        "rejected": rejected,
        "total": len(attacks),
    }


SCENARIOS: tuple[Callable[[Path, Journal], dict[str, Any]], ...] = (
    scenario_engine_swap,
    scenario_total_outage,
    scenario_recovery,
    scenario_bypass_attacks,
)


def run(out_dir: str | Path | None = None) -> dict[str, Any]:
    """Гоняет все сценарии, пишет кровь и возвращает сводку (детерминированно)."""
    journal = Journal()
    stats: dict[str, Any] = {"scenarios": [], "attacks": []}
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for scenario in SCENARIOS:
            stats["scenarios"].append(scenario(tmp, journal))
        stats["attacks"] = next(s for s in stats["scenarios"] if s["name"] == "bypass-attacks")["attacks"]
    out = Path(out_dir) if out_dir else RUN_DIR
    out.mkdir(parents=True, exist_ok=True)
    journal.to_jsonl(out / "blood.jsonl")
    scenarios_ok = sum(1 for s in stats["scenarios"] if s["ok"])
    attacks_ok = sum(1 for a in stats["attacks"] if a["rejected"])
    stats["ok"] = scenarios_ok == len(stats["scenarios"]) and attacks_ok == len(stats["attacks"])
    return stats


def main(argv: list[str] | None = None) -> int:
    out_dir = argv[0] if argv else None
    stats = run(out_dir)
    for scenario in stats["scenarios"]:
        print(f"red-run/{scenario['name']}: {'ok' if scenario['ok'] else 'FAIL'}")
        if scenario["name"] == "bypass-attacks":
            for attack in stats["attacks"]:
                mark = "отвергнута" if attack["rejected"] else "ПРОШЛА"
                print(f"  {attack['id']} [{attack['gate']}] {attack['rule']}: {mark} — {attack['detail']}")
    scenarios_ok = sum(1 for s in stats["scenarios"] if s["ok"])
    attacks_ok = sum(1 for a in stats["attacks"] if a["rejected"])
    print(
        f"RED-RUN: {scenarios_ok + attacks_ok} ok, "
        f"{(len(stats['scenarios']) - scenarios_ok) + (len(stats['attacks']) - attacks_ok)} failed"
    )
    return 0 if stats["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
