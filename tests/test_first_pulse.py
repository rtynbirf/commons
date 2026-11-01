"""Приёмка: первый живой пульс (DoD M1) — артефакты подлинные и реконструируемые.

Артефакты прогона живут в runs/*-first-pulse/ и коммитятся: кровь — вещественное
доказательство того, что организм один раз уже работал. Эта приёмка гарантирует,
что коммитнутая кровь валидна по схеме, трейс восстанавливается (G1) и не было
ни одного события без цены. Воспроизведение прогона: scripts/first_pulse.py
(требует markitdown-mcp локально; сам тест его не запускает — CI-безопасно).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from blood.envelope import validate

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_DIRS = sorted((REPO_ROOT / "runs").glob("*-first-pulse"))


@pytest.fixture(scope="module")
def pulse() -> dict[str, object]:
    """Артефакты первого пульса: путь к директории, конверты, текст на выходе."""
    if not RUN_DIRS:
        pytest.skip("пульса ещё не было — запусти scripts/first_pulse.py")
    run_dir = RUN_DIRS[-1]
    lines = (run_dir / "blood.jsonl").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines if line.strip()]
    return {
        "dir": run_dir,
        "events": events,
        "output": (run_dir / "output.md").read_text(encoding="utf-8"),
    }


def test_pulse_artifacts_exist(pulse: dict[str, object]) -> None:
    run_dir: Path = pulse["dir"]  # type: ignore[assignment]
    for artifact in ("blood.jsonl", "output.md", "report.md", "input/pulse-input.docx"):
        assert (run_dir / artifact).is_file(), f"нет артефакта пульса: {artifact}"


def test_every_envelope_valid_by_schema(pulse: dict[str, object]) -> None:
    events: list[dict] = pulse["events"]  # type: ignore[assignment]
    assert len(events) >= 4, "кровь пуста: живого прогона не было"
    for event in events:
        validate(event)  # EnvelopeError = кровь подделана после прогона


def test_g1_reconstruction(pulse: dict[str, object]) -> None:
    events: list[dict] = pulse["events"]  # type: ignore[assignment]
    trace_ids = {event["trace_id"] for event in events}
    assert len(trace_ids) == 1, "в одном прогоне больше одного trace_id"
    types = [event["type"] for event in events]
    assert types == ["plan", "act", "observe", "reflect"], f"цепь нарушена: {types}"
    forbidden = {"veto", "error", "halt", "security.violation"} & set(types)
    assert not forbidden, f"пульс закончился отказным режимом: {forbidden}"


def test_no_empty_cost(pulse: dict[str, object]) -> None:
    events: list[dict] = pulse["events"]  # type: ignore[assignment]
    for event in events:
        assert set(event["cost"]) == {"tokens_in", "tokens_out", "seconds"}, (
            f"событие {event['type']} без полной цены: {event['cost']}"
        )
    act = [event for event in events if event["type"] == "act"][0]
    assert act["cost"]["seconds"] > 0, "вызов органа без измеренного времени"


def test_act_is_real_sensory_conversion(pulse: dict[str, object]) -> None:
    events: list[dict] = pulse["events"]  # type: ignore[assignment]
    act = [event for event in events if event["type"] == "act"][0]
    observe = [event for event in events if event["type"] == "observe"][0]
    assert act["organ"] == "markitdown"
    assert act["payload"]["tool"] == "convert_to_markdown"
    result = observe["payload"]["result"]
    assert result["is_error"] is False
    assert result["text"].strip(), "сенсорика вернула пустоту"


def test_output_matches_blood(pulse: dict[str, object]) -> None:
    events: list[dict] = pulse["events"]  # type: ignore[assignment]
    observe = [event for event in events if event["type"] == "observe"][0]
    assert pulse["output"] == observe["payload"]["result"]["text"], (
        "output.md не совпадает с кровью: артефакты разошлись"
    )
    assert "проба сенсорики" in str(pulse["output"]), "организм не увидел свой входной документ"
