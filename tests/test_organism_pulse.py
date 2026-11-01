"""Приёмка: пульс организма — сенсорика + метаболизм в одном трейсе (DoD M1).

Артефакты: runs/*-organism-pulse/ (коммитнуты как вещественное доказательство,
ADR-0005). Воспроизведение: scripts/organism_pulse.py (нужны markitdown-mcp и
живой llama-server на LLAMA_SERVER_URL; сам тест ничего не запускает — CI-безопасно).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from blood.envelope import validate

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_DIRS = sorted((REPO_ROOT / "runs").glob("*-organism-pulse"))


@pytest.fixture(scope="module")
def pulse() -> dict[str, object]:
    if not RUN_DIRS:
        pytest.skip("пульса ещё не было — запусти scripts/organism_pulse.py")
    run_dir = RUN_DIRS[-1]
    events = [json.loads(line) for line in (run_dir / "blood.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    return {"dir": run_dir, "events": events, "output": (run_dir / "output.md").read_text(encoding="utf-8")}


def test_trace_has_two_organs(pulse: dict[str, object]) -> None:
    events: list[dict] = pulse["events"]  # type: ignore[assignment]
    acts = [event for event in events if event["type"] == "act"]
    assert {event["organ"] for event in acts} == {"markitdown", "llama.cpp"}, (
        f"в трейсе не два органа: {[event['organ'] for event in acts]}"
    )


def test_full_sequence_reconstructs(pulse: dict[str, object]) -> None:
    events: list[dict] = pulse["events"]  # type: ignore[assignment]
    assert len({event["trace_id"] for event in events}) == 1, "больше одного trace_id"
    types = [event["type"] for event in events]
    assert types == ["plan", "act", "observe", "reflect"] * 2, f"цепь нарушена: {types}"
    assert not ({"veto", "error", "halt", "security.violation"} & set(types)), "отказной режим в трейсе"
    for event in events:
        validate(event)


def test_metabolism_tokens_in_blood(pulse: dict[str, object]) -> None:
    """Второй закон экономики: токены метаболизма не выдуманы и не потеряны."""
    events: list[dict] = pulse["events"]  # type: ignore[assignment]
    act = [event for event in events if event["type"] == "act" and event["organ"] == "llama.cpp"][0]
    assert act["cost"]["tokens_in"] > 0, "промпт не посчитан сервером"
    assert act["cost"]["tokens_out"] > 0, "ответ не посчитан сервером"
    assert act["cost"]["seconds"] > 0
    for event in events:
        assert set(event["cost"]) == {"tokens_in", "tokens_out", "seconds"}


def test_sensory_result_fed_to_metabolism(pulse: dict[str, object]) -> None:
    """Обмен внутри трейса: выход сенсорики вошёл в промпт метаболизма."""
    events: list[dict] = pulse["events"]  # type: ignore[assignment]
    sensory_observe = [event for event in events if event["type"] == "observe" and event["organ"] == "markitdown"][0]
    metabolism_act = [event for event in events if event["type"] == "act" and event["organ"] == "llama.cpp"][0]
    sensory_text = sensory_observe["payload"]["result"]["text"]
    assert sensory_text in metabolism_act["payload"]["payload"]["prompt"], "метаболизм не увидел выход сенсорики"


def test_output_matches_blood(pulse: dict[str, object]) -> None:
    events: list[dict] = pulse["events"]  # type: ignore[assignment]
    metabolism_observe = [event for event in events if event["type"] == "observe" and event["organ"] == "llama.cpp"][0]
    summary = metabolism_observe["payload"]["result"]["response"]
    assert summary.strip() in str(pulse["output"]), "output.md разошёлся с кровью"
