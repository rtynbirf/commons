"""Приёмка SPEC-0003: конверт крови и append-only журнал."""

from __future__ import annotations

import pytest

from blood.envelope import Cost, EnvelopeError, load_schema, make, new_trace_id, validate
from blood.journal import Journal

TRACE = new_trace_id()


def valid_envelope() -> dict:
    return make("act", "synapse", "ollama", TRACE, {"tool": "generate"}, Cost(10, 5, 0.5))


def test_envelope_validates_against_schema() -> None:
    envelope = valid_envelope()
    validate(envelope)
    assert envelope["cost"] == {"tokens_in": 10, "tokens_out": 5, "seconds": 0.5}
    assert envelope["ts"].endswith("Z")


def test_event_without_cost_is_invalid() -> None:
    envelope = valid_envelope()
    del envelope["cost"]  # событие без цены недействительно (SPEC-0003 п.3)
    with pytest.raises(EnvelopeError):
        validate(envelope)


def test_event_with_negative_cost_is_invalid() -> None:
    with pytest.raises(EnvelopeError):
        make("act", "synapse", "ollama", TRACE, {}, Cost(-1, 0, 0))


def test_unknown_event_type_is_invalid() -> None:
    with pytest.raises(EnvelopeError):
        make("teleport", "synapse", "ollama", TRACE, {}, Cost())


def test_bad_timestamp_is_invalid() -> None:
    envelope = valid_envelope()
    envelope["ts"] = "вчера"
    with pytest.raises(EnvelopeError):
        validate(envelope)


def test_journal_is_append_only_and_reconstructs_session() -> None:
    journal = Journal()
    for _ in range(3):
        journal.append(valid_envelope())
    events = journal.all()
    assert len(events) == 3
    assert [e["type"] for e in events] == ["act", "act", "act"]
    assert journal.totals(TRACE) == Cost(30, 15, 1.5)


def test_journal_rejects_invalid_envelope() -> None:
    journal = Journal()
    broken = valid_envelope()
    broken["extra_field"] = "не по схеме"  # additionalProperties: false
    with pytest.raises(EnvelopeError):
        journal.append(broken)
    assert len(journal) == 0


def test_schema_itself_is_wired_to_spec_contract() -> None:
    schema = load_schema()
    assert set(schema["required"]) == {"id", "ts", "type", "source", "organ", "trace_id", "payload", "cost"}
    assert set(schema["properties"]["cost"]["required"]) == {"tokens_in", "tokens_out", "seconds"}
