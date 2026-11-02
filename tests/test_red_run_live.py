# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмка живого red-run (волна №10, W-0012): харнесс повторяем, кровь валидна,
атаки отбиты живьём, находка о детёнышах процессов зафиксирована как ожидаемая.

Харнесс гоняется в tmp целиком (без LLM: настоящий fs, настоящий сокет, настоящий
детёныш) и коммиченная кровь валидируется по схеме. Если страж однажды увидит
детёнышей (кандидат SPEC-0002 v0.6.0 исполнен) — приёмка честно покраснет и
потребует обновить саму себя.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from blood.envelope import validate

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_DIR = REPO_ROOT / "runs" / "2026-11-02-wave10-red-run-live"
HARNESS = RUN_DIR / "run.py"
BLOOD = RUN_DIR / "blood.jsonl"
STATS = RUN_DIR / "stats.json"

_spec = importlib.util.spec_from_file_location("w10_red_live", HARNESS)
w10_red = importlib.util.module_from_spec(_spec)
sys.modules["w10_red_live"] = w10_red
_spec.loader.exec_module(w10_red)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_live_red_run_is_green_with_children_finding(tmp_path: Path) -> None:
    stats = w10_red.run(tmp_path)

    assert stats["ok"], stats
    assert [s["name"] for s in stats["scenes"]] == [f"C{i}" for i in range(1, 10)], "девять живых сцен"
    assert len(stats["findings"]) == 1, "ровно одна ожидаемая находка"

    finding = stats["findings"][0]
    assert finding["scene"] == "С3" and finding["hits"] >= 1, "детёныш соединился по-настоящему"
    assert "v0.5" in finding["candidate"], "находка обязана вести в SPEC-0002 v0.6.0"

    by_name = {s["name"]: s for s in stats["scenes"]}
    assert by_name["C1"]["control_crime"] is True, "контроль: голый диспетчер создал файл живьём"
    assert by_name["C2"]["control_leak_hits"] == 1, "контроль: утечка состоялась живьём"
    assert by_name["C5"]["exit_code"] == 0, "PID 1 умер по-записанному"
    assert by_name["C6"]["envelopes"] == 8, "кровь пережила смерть процесса без потерь"


def test_committed_live_red_blood_is_valid_and_complete() -> None:
    assert BLOOD.exists(), "кровь живого red-run обязана быть в репозитории"
    events = _read_jsonl(BLOOD)

    assert len(events) == 34
    for envelope in events:
        validate(envelope)  # SPEC-0003: конверт вне схемы не кровь

    types = {e["type"] for e in events}
    assert {"plan", "act", "observe", "reflect", "halt", "security.violation", "veto",
            "error", "organ.replace", "alert", "boot", "organ.health", "shutdown"} <= types

    traces = {e["trace_id"] for e in events}
    # кровь детёныша С6 (w10r-sc6-child) живёт в его собственном файле — она не в этой крови;
    # PID 1 в С5 пишет под случайным trace_id новой сессии — потому проверка на подмножество
    assert {"w10r-sc1-fs", "w10r-sc2-net", "w10r-sc3-children", "w10r-sc4-replace", "w10r-sc4-bind",
            "w10r-sc5-outage", "w10r-sc7-budget", "w10r-sc9-ghost", "w10r-sc9-tool"} <= traces

    # С1+С2: страж прервал два живых греха ДО факта; С3: ни одного security.violation — находка в крови
    violations = [e for e in events if e["type"] == "security.violation"]
    assert {e["trace_id"] for e in violations} == {"w10r-sc1-fs", "w10r-sc2-net"}
    sc3 = [e["type"] for e in events if e["trace_id"] == "w10r-sc3-children"]
    assert "act" in sc3 and "security.violation" not in sc3, "находка С3 обязана жить в крови как обычный act"

    sc7 = [e for e in events if e["trace_id"] == "w10r-sc7-budget"]
    assert sum(1 for e in sc7 if e["type"] == "alert" and e["organ"] == "greedy") == 2, "per-call перерасход пойман дважды"
    assert sum(1 for e in sc7 if e["type"] == "act") == 2, "третий шаг не оплатился: граница включена"
    # PID 1 (С5) пишет под случайным trace_id новой сессии после смерти журнала — ищем по типу
    assert sum(1 for e in events if e["type"] == "shutdown" and e["payload"].get("reason") == "max_beats") == 1


def test_committed_red_stats_match_blood() -> None:
    stats = json.loads(STATS.read_text(encoding="utf-8"))
    assert stats["ok"] is True
    assert stats["blood_envelopes"] == len(_read_jsonl(BLOOD)), "статистика не врёт о количестве конвертов"
    assert [s["name"] for s in stats["scenes"]] == [f"C{i}" for i in range(1, 10)]
