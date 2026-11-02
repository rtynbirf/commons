# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмка красного прогона (0.17.0): харнесс повторяем, кровь валидна, атаки отбиты.

Красный прогон (runs/2026-11-02-red-run/) закрывает каркасный уровень
аудит-матрицы внешней рецензии: замена органа (G2), одновременный отказ
(degrade + HALT), восстановление из крови (G1), обход белых списков (10/10
отвергнут). Приёмка гоняет харнесс в tmp и валидирует пролитую кровь
репозитория: откат любого белого списка красит PR.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from blood.envelope import validate

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS = REPO_ROOT / "runs" / "2026-11-02-red-run" / "run.py"
BLOOD = REPO_ROOT / "runs" / "2026-11-02-red-run" / "blood.jsonl"

_spec = importlib.util.spec_from_file_location("red_run", HARNESS)
red_run = importlib.util.module_from_spec(_spec)
sys.modules["red_run"] = red_run
_spec.loader.exec_module(red_run)


def test_red_run_is_green_and_repeatable(tmp_path: Path) -> None:
    stats = red_run.run(tmp_path)

    assert stats["ok"], stats
    scenarios = {s["name"]: s for s in stats["scenarios"]}

    swap = scenarios["engine-swap"]
    assert swap["shape"] == ["plan", "act", "observe", "reflect"] * 2
    assert swap["cost_a"] != swap["cost_b"], "движки обязаны давать разную цену"
    assert swap["brainstem_untouched"]

    outage = scenarios["total-outage"]
    assert outage["loop_types"] == ["error", "plan", "error", "reflect"]
    assert outage["pid1_exit"] == 0 and outage["no_crash"]
    assert outage["unhealthy_beats"] >= 4

    recovery = scenarios["recovery"]
    assert recovery["skipped"] == 0
    assert recovery["traces_reconstructed"] == ["red-swap-a", "red-swap-b"]

    assert len(stats["attacks"]) == 10
    assert all(a["rejected"] for a in stats["attacks"]), stats["attacks"]


def test_committed_red_blood_is_valid_and_complete() -> None:
    assert BLOOD.exists(), "кровь красного прогона обязана быть в репозитории"
    events = [json.loads(line) for line in BLOOD.read_text(encoding="utf-8").splitlines() if line.strip()]

    assert len(events) >= 30
    for envelope in events:
        validate(envelope)  # SPEC-0003: конверт вне схемы не кровь

    types = {e["type"] for e in events}
    assert {"plan", "act", "observe", "reflect", "error", "boot", "organ.health", "shutdown", "veto", "security.violation"} <= types

    traces = {e["trace_id"] for e in events}
    assert {"red-swap-a", "red-swap-b", "red-outage", "red-attacks"} <= traces

    verdicts = [e for e in events if e["source"] == "red-run"]
    assert len(verdicts) == 6, "шесть атак внешних барьеров — шесть конвертов"
    assert all(e["payload"]["verdict"] in ("rejected", "gate-held") for e in verdicts)
    assert all(e["payload"]["verdict"] == "rejected" for e in verdicts if e["payload"]["attack"] != "A6b")


def test_swap_traces_have_identical_shape_but_different_engines() -> None:
    events = [json.loads(line) for line in BLOOD.read_text(encoding="utf-8").splitlines() if line.strip()]

    def shape(trace_id: str) -> list[tuple[str, str]]:
        return [(e["type"], e["source"]) for e in events if e["trace_id"] == trace_id]

    assert shape("red-swap-a") == shape("red-swap-b"), "ствол не заметил смены движка"

    def tokens(trace_id: str) -> int:
        return sum(e["cost"]["tokens_in"] for e in events if e["trace_id"] == trace_id)

    assert tokens("red-swap-a") != tokens("red-swap-b"), "движок другой — цена другая"
