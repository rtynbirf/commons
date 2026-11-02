# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Живой red-run (волна №10, W-0012): орган, пытающийся обойти ствол, — на живом хосте.

Каркас 0.17.0 гонял атаки на подставках; здесь каждый грех настоящий: реальная
запись файла, реальный сокет, реальный детёныш-процесс, реальная смерть процесса
и восстановление из настоящей крови на диске.

Сцены:
  С1 ренегат fs живьём: при fs: read-only РЕАЛЬНО пишет — страж прерывает ДО,
     файла нет; контроль: тот же ренегат у голого диспетчера файл создаёт (увидели грех живьём);
  С2 ренегат сети живьём: при network: none РЕАЛЬНО соединяется — страж прерывает ДО,
     живой свидетель не видел ни одного соединения; контроль: соединение состоялось, контент получен;
  С3 детёныши процессов (перевёрнута волной №12, SPEC-0002 v0.7.0): орган заявляет
     network: none + process: spawn — детёныш наследует страж (COMMONS_AUTHORITY + sitecustomize),
     его соединение прервано, свидетель не видел ни одного, честный родитель отдал нарушение в кровь;
  С4 замена при живом падении + отказ самозванцу и безымянному (п.9), прежняя привязка жива;
  С5 одновременный отказ: орган и резерв мертвы — OrganUnavailable, reflect+halt (G1-полный),
     PID 1 дышит по мёртвым органам и умирает по-записанному;
  С6 восстановление из крови живьём: подпроцесс проливает кровь на диск и умирает без прощания,
     replay из файла реконструирует трейсы — skipped=0;
  С7 перерасход живьём: per-call лимит → alert (вызов оплачен), трейс-бюджет → halt до следующего шага;
  С8 fail-closed живьём: неисполнимая грамматика не даёт шлюзу стартовать; живой манифест дома стартует;
  С9 белые списки манифеста: орган-призрак и инструмент вне манифеста — veto в крови.

Запуск из корня репо: python runs/2026-11-02-wave10-red-run-live/run.py
Кровь — runs/2026-11-02-wave10-red-run-live/blood.jsonl (append-only, порядок сцен = порядок строк).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
RUN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(RUN_DIR))  # манифест грузит адаптеры по имени "organs:..."

import yaml  # noqa: E402

from blood.envelope import validate  # noqa: E402
from blood.journal import Journal  # noqa: E402
from brainstem import Budget, Loop, Step  # noqa: E402
from brainstem.pid1 import PID1  # noqa: E402
from memory.engine import DefaultMemory  # noqa: E402
from memory.replay import replay  # noqa: E402
from synapse.authority import AuthorityViolation  # noqa: E402
from synapse.gateway import (  # noqa: E402
    AuthorityViolation,
    Gateway,
    GatewayConfigError,
    OrganUnavailable,
    SynapseVeto,
)

import red_organs as organs  # noqa: E402  (уникальное имя: в корне дома живёт пакет organs/)

BLOOD_PATH = RUN_DIR / "blood.jsonl"

VERDICTS: list[str] = []
FINDINGS: list[dict[str, Any]] = []


def verdict(kind: str, text: str) -> None:
    marker = {"g": "[ЗЕЛЁНО]", "r": "[КРАСНО]", "f": "[ФАКТ]"}[kind]
    line = f"{marker} {text}"
    print(line)
    VERDICTS.append(line)


def manifest_file(tmp: Path, organs_list: list[dict[str, Any]], subs: dict[str, list[str]] | None = None) -> Path:
    doc = {"version": "w10-red", "updated": "2026-11-02", "transport_default": "stdio", "organs": organs_list}
    if subs:
        doc["substitutions"] = subs
    path = tmp / "mcp-manifest.yaml"
    path.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return path


def entry(name: str, adapter_cls: str, *, tools: list[str] | None = None,
          authority: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    base = {
        "name": name,
        "system": "senses",
        "mode": "dependency",
        "upstream": f"live://w10/{name}",
        "license": "Apache-2.0",
        "transport": "stdio",
        "command": "live",
        "healthcheck": "живой орган",
        "tools": tools or ["echo"],
        "authority": authority or {"fs": "read-only", "network": "none", "process": "none"},
        "adapter": adapter_cls,
    }
    base.update(extra)
    return base


def types_of(journal: Journal, trace_id: str) -> list[str]:
    return [e["type"] for e in journal.by_trace(trace_id)]


def bare_dispatch(adapters: dict[str, Any], organ: str, tool: str, payload: dict[str, Any]) -> tuple[bool, Any]:
    """Голый диспетчер (контроль обхода ствола): глотает всё, ничего не пишет."""
    adapter = adapters.get(organ)
    if adapter is None or not adapter.health():
        return False, None
    try:
        result, _cost = adapter.invoke(tool, payload)
        return True, result
    except Exception as exc:  # noqa: BLE001 — тихая порча
        return False, f"{type(exc).__name__}: {exc}"


# --- сцены ---

def scene_c1_renegade_file(tmp: Path, journal: Journal) -> dict[str, Any]:
    contraband = tmp / "contraband.txt"
    path = manifest_file(tmp, [entry("renegade", "red_organs:LiveRenegadeFile", tools=["smuggle_file"])])
    gw = Gateway(path, journal)
    trace = "w10r-sc1-fs"
    interrupted = False
    try:
        gw.call("renegade", "smuggle_file", {"path": str(contraband)}, trace)
    except AuthorityViolation as exc:
        interrupted = True
        verdict("f", f"С1: страж прервал живую запись: {exc}")
    assert interrupted, "С1: ренегат не прерван"
    assert not contraband.exists(), "С1: контрабанда записана на диск!"
    crimes = gw._adapters["renegade"].crimes
    assert not crimes, f"С1: ренегат успел совершить грех: {crimes}"
    kinds = types_of(journal, trace)
    assert "security.violation" in kinds and "act" not in kinds, kinds

    # контроль: тот же класс органа у голого диспетчера — грех состоится живьём
    bare_renegade = organs.LiveRenegadeFile({"name": "renegade"})
    ok, _res = bare_dispatch({"renegade": bare_renegade}, "renegade", "smuggle_file", {"path": str(contraband)})
    assert ok and contraband.exists() and bare_renegade.crimes, "С1: контроль не доказал обход"
    contraband.unlink()
    verdict("g", "С1: живая запись прервана ДО факта (файла нет, security.violation, act нет); "
                 "тот же ренегат без ствола файл создал — грех увидели своими глазами")
    return {"trace": trace, "control_crime": True}


def scene_c2_renegade_net(tmp: Path, journal: Journal) -> dict[str, Any]:
    path = manifest_file(tmp, [entry("renegade", "red_organs:LiveRenegadeNet", tools=["phone_home"])])
    gw = Gateway(path, journal)
    with organs.ControlServer() as server:
        trace = "w10r-sc2-net"
        hits_before = len(server.hits)
        interrupted = False
        try:
            gw.call("renegade", "phone_home", {"url": server.url}, trace)
        except AuthorityViolation as exc:
            interrupted = True
            verdict("f", f"С2: страж прервал живое соединение: {exc}")
        assert interrupted, "С2: соединение не прервано"
        assert len(server.hits) == hits_before, "С2: свидетель ВИДЕЛ соединение — страж опоздал"
        kinds = types_of(journal, trace)
        assert "security.violation" in kinds and "act" not in kinds, kinds

        bare_renegade = organs.LiveRenegadeNet({"name": "renegade"})
        ok, res = bare_dispatch({"renegade": bare_renegade}, "renegade", "phone_home", {"url": server.url})
        leaks = len(server.hits) - hits_before
        assert ok and leaks >= 1 and isinstance(res, dict) and "4242" in str(res.get("phoned", "")), "С2: контроль не доказал утечку"
    verdict("g", "С2: живое соединение прервано ДО факта (свидетель не видел ни одного; security.violation, act нет); "
                 "тот же ренегат без ствола соединился по-настоящему и получил контент — утечка живьём")
    return {"trace": trace, "control_leak_hits": 1}


def scene_c3_children(tmp: Path, journal: Journal, server: "organs.ControlServer", hits_before: int) -> dict[str, Any]:
    """Перевёрнута (SPEC-0002 v0.7.0, волна №12): детёныш живёт под стражем — соединение прервано,
    свидетель чист, честный родитель отдал нарушение детёныша в кровь как security.violation."""
    path = manifest_file(tmp, [entry("smuggler", "red_organs:LiveSpawnChild", tools=["fetch_via_child"],
                                     authority={"fs": "read-only", "network": "none", "process": "spawn"})])
    gw = Gateway(path, journal)
    trace = "w10r-sc3-children"
    interrupted = False
    try:
        gw.call("smuggler", "fetch_via_child", {"url": server.url}, trace)
    except AuthorityViolation:  # честный родитель не глотает падение детёныша
        interrupted = True
    hits_after = len(server.hits) - hits_before
    kinds = types_of(journal, trace)
    assert interrupted, "С3: детёныш не прерван — страж ослеп? граница процесса вернулась"
    assert hits_after == 0, f"С3: свидетель видел {hits_after} соединений детёныша"
    assert "security.violation" in kinds, f"С3: нарушение детёныша не дошло до крови: {kinds}"
    verdict("g", "С3: детёныш под стражем (SPEC-0002 v0.7.0, волна №12) — соединение прервано в детёныше "
                 f"(свидетель не видел ни одного из {hits_after}), честный родитель отдал security.violation в кровь")
    return {"trace": trace, "child_hits": 0, "child_blocked": True}


def scene_c4_replace_and_identity(tmp: Path, journal: Journal) -> dict[str, Any]:
    path = manifest_file(tmp, [entry("fallen", "red_organs:LiveFallen", die_on=1), entry("reserve", "red_organs:LiveEcho")],
                         subs={"fallen": ["reserve"]})
    gw = Gateway(path, journal)
    trace = "w10r-sc4-replace"
    result = gw.call("fallen", "echo", {"data": "живой отказ"}, trace)
    assert result is not None, "С4: резерв не ответил живому отказу"
    kinds = types_of(journal, trace)
    assert "error" in kinds and "organ.replace" in kinds, kinds

    impostor = organs.LiveEcho({"name": "reserve"})
    refused = False
    try:
        gw.bind_adapter("fallen", impostor)
    except GatewayConfigError:
        refused = True
    assert refused, "С4: самозванец принят"
    nameless = organs.LiveEcho({"name": "fallen"})
    nameless.entry = {}
    refused2 = False
    try:
        gw.bind_adapter("fallen", nameless)
    except GatewayConfigError:
        refused2 = True
    assert refused2, "С4: безымянный принят"
    result2 = gw.call("fallen", "echo", {"data": "после отказов"}, "w10r-sc4-bind")
    assert result2 is not None, "С4: прежняя привязка сломана отказами"
    verdict("g", "С4: живой отказ обслужен резервом (error → organ.replace → act); самозванец и безымянный "
                 "отклонены до мутации привязки (п.9), прежняя привязка жива")
    return {"trace": trace}


def scene_c5_total_outage(tmp: Path, journal: Journal) -> dict[str, Any]:
    class BrokenMemory:
        def observe(self, envelope: dict[str, Any]) -> None:
            raise RuntimeError("память умерла")

        def context(self, intent: str, k: int = 3) -> list[dict[str, Any]]:
            raise RuntimeError("память умерла")

    path = manifest_file(tmp, [entry("sense-a", "red_organs:LiveDead"), entry("reserve-b", "red_organs:LiveDead")],
                         subs={"sense-a": ["reserve-b"]})
    gw = Gateway(path, journal)
    gw.bind_adapter("sense-a", organs.LiveDead({"name": "sense-a"}))
    gw.bind_adapter("reserve-b", organs.LiveDead({"name": "reserve-b"}))
    trace = "w10r-sc5-outage"
    loop = Loop(gw, journal, memory=BrokenMemory())
    plan = [Step(organ="sense-a", tool="echo", payload={"x": 1}, intent="посмотреть мир")]
    satisfied = loop.run(plan, trace_id=trace)
    kinds = types_of(journal, trace)
    assert satisfied is False, "С5: одновременный отказ не остановил цикл"
    assert "halt" in kinds and "reflect" in kinds, kinds
    assert any(e["type"] == "error" and e["payload"].get("reason") == "memory_unavailable" for e in journal.by_trace(trace)), kinds

    pid = PID1(gw, journal, interval=0.05)
    exit_code = pid.run(max_beats=2)  # возвращает код выхода, не биения; при смерти закрывает журнал (SPEC-0004)
    shutdown = [e for e in journal.by_type("shutdown") if e["payload"].get("reason") == "max_beats"]
    dead_beats = [e for e in journal.by_type("organ.health") if not e["payload"].get("healthy", True)]
    assert exit_code == 0 and shutdown, "С5: PID 1 не умер по-записанному"
    assert len(dead_beats) >= 4, f"С5: мёртвые органы не опрашивались: {len(dead_beats)}"
    beats = shutdown[0]["payload"].get("beats", "?")
    verdict("g", f"С5: орган и резерв мертвы, память умерла — цикл жив: error(degrade) → reflect+halt (G1-полный), "
                 f"PID 1 отстучал {beats} такта по мёртвым органам и умер по-записанному (exit {exit_code})")
    return {"trace": trace, "beats": beats, "exit_code": exit_code}


def scene_c6_recovery(tmp: Path, journal: Journal) -> dict[str, Any]:
    """Живая смерть: подпроцесс проливает кровь на диск и умирает без прощания."""
    child_blood = tmp / "blood-live.jsonl"
    child_code = f"""
import sys, os
sys.path.insert(0, {str(REPO)!r})
sys.path.insert(0, {str(RUN_DIR)!r})
import yaml
from blood.journal import Journal
from brainstem import Loop, Step
from synapse.gateway import Gateway
manifest = {{
    "version": "w10-red-child", "updated": "2026-11-02", "transport_default": "stdio",
    "organs": [{{"name": "heart", "system": "senses", "mode": "dependency", "upstream": "live://child",
                 "license": "Apache-2.0", "transport": "stdio", "command": "live", "healthcheck": "живой орган",
                 "tools": ["echo"], "authority": {{"fs": "read-only", "network": "none", "process": "none"}},
                 "adapter": "red_organs:LiveEcho"}}],
}}
path = {str(tmp / "child-manifest.yaml")!r}
open(path, "w", encoding="utf-8").write(yaml.safe_dump(manifest, allow_unicode=True))
j = Journal(); j.attach({str(child_blood)!r})
gw = Gateway(path, j)
loop = Loop(gw, j)
loop.run([Step(organ="heart", tool="echo", payload={{"beat": 1}}, intent="первый такт"),
          Step(organ="heart", tool="echo", payload={{"beat": 2}}, intent="второй такт")],
         trace_id="w10r-sc6-child")
os._exit(0)  # смерть без прощания: attach уже на диске (SPEC-0004 п.5)
"""
    proc = subprocess.run([sys.executable, "-c", child_code], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"С6: подпроцесс умер криво: {proc.stderr[-300:]}"
    lines = child_blood.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 8, f"С6: кровь подпроцесса неполна: {len(lines)} конвертов (ожидался полный цикл 2×4)"

    engine = DefaultMemory(tmp / "mem")
    report = replay(child_blood, index=engine.index, graph=engine.graph)
    events = [json.loads(line) for line in lines if line.strip()]
    for envelope in events:
        validate(envelope)
    child_kinds = [e["type"] for e in events if e["trace_id"] == "w10r-sc6-child"]
    assert report["skipped"] == 0 and report["envelopes"] == len(events), report
    assert child_kinds == ["plan", "act", "observe", "reflect"] * 2, child_kinds
    assert report["graph"]["nodes"] > 0
    verdict("g", f"С6: процесс умер без прощания — {len(events)} конвертов на диске, replay реконструировал "
                 f"оба такта (skipped=0, граф {report['graph']['nodes']} узлов), каждый конверт валиден схемой")
    return {"trace": "w10r-sc6-child", "envelopes": len(events)}


def scene_c7_overspend(tmp: Path, journal: Journal) -> dict[str, Any]:
    path = manifest_file(tmp, [entry("greedy", "red_organs:LiveOverspender")])
    gw = Gateway(path, journal)
    trace = "w10r-sc7-budget"
    loop = Loop(gw, journal, organ_budgets={"greedy": Budget(tokens_in=100)})
    plan = [Step(organ="greedy", tool="echo", payload={"i": i}, intent="тратить") for i in range(3)]
    satisfied = loop.run(plan, trace_id=trace, budget=Budget(tokens_in=200))
    kinds = types_of(journal, trace)
    alerts = [e for e in journal.by_trace(trace) if e["type"] == "alert" and e["organ"] == "greedy"]
    halts = [e for e in journal.by_trace(trace) if e["type"] == "halt"]
    assert satisfied is False, "С7: трейс-бюджет не остановил трату"
    assert len(alerts) == 2, f"С7: per-call перерасход не замечен дважды: {len(alerts)}"
    assert len(halts) == 1 and "бюджет исчерпан" in halts[0]["payload"]["reason"], halts
    assert kinds.count("act") == 2, kinds  # третий шаг не оплатился: граница включена
    verdict("g", "С7: живой перерасход пойман дважды: per-call (вызов оплачен, alert с именем органа ×2) "
                 "и трейс-бюджет (halt до третьего шага, 150+150 >= 200)")
    return {"trace": trace}


def scene_c8_fail_closed(tmp: Path, journal: Journal) -> dict[str, Any]:
    bad_grammars = [
        {"fs": "read-only-input-dir", "network": "none", "process": "none"},
        {"fs": "walrus", "network": "none", "process": "none"},
        {"fs": "none", "network": {"hosts": []}, "process": "none"},
    ]
    refused = 0
    for authority in bad_grammars:
        path = manifest_file(tmp, [entry("bad", "red_organs:LiveEcho", authority=authority)])
        try:
            Gateway(path)
        except GatewayConfigError:
            refused += 1
    assert refused == len(bad_grammars), "С8: грамматика пропустила неисполнимые ярлыки"
    home = Gateway(REPO / "synapse" / "mcp-manifest.yaml", journal)
    verdict("g", f"С8: три неисполнимые грамматики не дали шлюзу стартовать (fail-closed); "
                 f"живой манифест дома стартует: {', '.join(home.organ_names)}")
    return {"refused": refused}


def scene_c9_whitelists(tmp: Path, journal: Journal) -> dict[str, Any]:
    path = manifest_file(tmp, [entry("honest", "red_organs:LiveEcho")])
    gw = Gateway(path, journal)
    trace_ghost, trace_tool = "w10r-sc9-ghost", "w10r-sc9-tool"
    ghost = tool = False
    try:
        gw.call("ghost", "echo", {}, trace_ghost)
    except SynapseVeto:
        ghost = True
    try:
        gw.call("honest", "exorcise", {}, trace_tool)
    except SynapseVeto:
        tool = True
    assert ghost and tool, "С9: белый список манифеста пропустил вызов"
    kinds_ghost, kinds_tool = types_of(journal, trace_ghost), types_of(journal, trace_tool)
    assert "veto" in kinds_ghost and "veto" in kinds_tool, (kinds_ghost, kinds_tool)
    verdict("g", "С9: орган-призрак и инструмент вне манифеста отвергнуты veto'м до вызова — белый список жив")
    return {"traces": [trace_ghost, trace_tool]}


def run(out_dir: Path) -> dict[str, Any]:
    VERDICTS.clear()  # приёмка гоняет харнесс в том же процессе — каждый прогон с чистого листа
    FINDINGS.clear()
    out_dir.mkdir(parents=True, exist_ok=True)
    blood = Journal()
    blood.attach(out_dir / "blood.jsonl")
    tmp = Path(tempfile.mkdtemp(prefix="w10-red-"))
    stats: dict[str, Any] = {"scenes": [], "findings": []}
    try:
        with organs.ControlServer() as server:
            stats["scenes"].append({"name": "C1", **scene_c1_renegade_file(tmp, blood)})
            stats["scenes"].append({"name": "C2", **scene_c2_renegade_net(tmp, blood)})
            hits_before = len(server.hits)
            stats["scenes"].append({"name": "C3", **scene_c3_children(tmp, blood, server, hits_before)})
        stats["scenes"].append({"name": "C4", **scene_c4_replace_and_identity(tmp, blood)})
        stats["scenes"].append({"name": "C5", **scene_c5_total_outage(tmp, blood)})
        # PID 1 при смерти закрывает журнал (SPEC-0004) — кровь продолжается новой сессией
        # того же append-only файла: сессии различаются trace_id, порядок строк = хронология
        blood.attach(out_dir / "blood.jsonl")
        stats["scenes"].append({"name": "C6", **scene_c6_recovery(tmp, blood)})
        stats["scenes"].append({"name": "C7", **scene_c7_overspend(tmp, blood)})
        stats["scenes"].append({"name": "C8", **scene_c8_fail_closed(tmp, blood)})
        stats["scenes"].append({"name": "C9", **scene_c9_whitelists(tmp, blood)})
        stats["findings"] = FINDINGS
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    lines = (out_dir / "blood.jsonl").read_text(encoding="utf-8").splitlines()
    for line in lines:
        validate(json.loads(line))
    stats["blood_envelopes"] = len(lines)
    stats["ok"] = (
        sum(1 for v in VERDICTS if v.startswith("[КРАСНО]")) == 0 and len(FINDINGS) == 0
    )  # находка С3 перевёрнута волной №12 (SPEC-0002 v0.7.0): ожидаемых красных больше нет
    return stats


def main() -> int:
    BLOOD_PATH.unlink(missing_ok=True)  # свежая кровь этого запуска
    stats = run(RUN_DIR)
    (RUN_DIR / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    red = sum(1 for v in VERDICTS if v.startswith("[КРАСНО]"))
    print()
    print(f"RED-RUN live: {len(VERDICTS) - red} зелёных, {red} красных (ожидаемая находка: {len(FINDINGS)}), "
          f"кровь: {stats['blood_envelopes']} конвертов")
    return 0 if stats["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
