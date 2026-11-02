"""Приёмка SPEC-0003 v0.7.0 п.10: конверт честного происхождения (W-0022, Ф-1.1).

Красный прогон волны №17 написан ДО кода: на нетронутом теле suites красен —
схема не знает полей происхождения (additionalProperties: false — fail-closed
честно роняет чужое поле), make() не принимает их, журнал не ставит stored_at.
"""

from __future__ import annotations

import uuid

import pytest

from blood.envelope import Cost, EnvelopeError, make, new_trace_id, validate
from blood.journal import Journal, verify

TRACE = new_trace_id()


def test_envelope_carries_triple_time() -> None:
    """Тройное время: когда случилось / когда увидено / когда записано."""
    envelope = make(
        "observe",
        "brainstem",
        "markitdown",
        TRACE,
        {"file": "notes.md"},
        Cost(1, 2, 0.3),
        occurred_at="2026-11-03T10:00:00Z",
        observed_at="2026-11-03T12:00:00Z",
    )
    validate(envelope)
    assert envelope["occurred_at"] == "2026-11-03T10:00:00Z"
    assert envelope["observed_at"] == "2026-11-03T12:00:00Z"


def test_occurred_at_null_is_honest_unknown() -> None:
    """Случилось, но момент неизвестен: null = UNKNOWN — не выдумка, не ноль."""
    envelope = make("observe", "brainstem", "self", TRACE, {}, Cost(), occurred_at=None)
    validate(envelope)
    assert envelope["occurred_at"] is None


def test_origin_classes_accepted() -> None:
    """Классы доверия и приватности ставятся конверту честным заявлением."""
    envelope = make(
        "act", "synapse", "ollama", TRACE, {}, Cost(),
        trust="verified", privacy="internal",
    )
    validate(envelope)
    assert envelope["trust"] == "verified"
    assert envelope["privacy"] == "internal"


@pytest.mark.parametrize("field", ["trust", "privacy"])
def test_unknown_class_is_fail_closed(field: str) -> None:
    """Неизвестный класс — fail-closed при записи (как неизвестный тип, ADR-0014)."""
    with pytest.raises(EnvelopeError):
        make("act", "synapse", "ollama", TRACE, {}, Cost(), **{field: "по-честному-не-знаю"})


def test_causation_id_names_semantic_parent() -> None:
    """causation_id — семантический родитель, не файловая цепочка prev_id."""
    parent = make("error", "brainstem", "ollama", TRACE, {}, Cost())
    child = make(
        "organ.replace", "brainstem", "reserve", TRACE, {}, Cost(),
        causation_id=parent["id"],
    )
    validate(child)
    assert child["causation_id"] == parent["id"]


def test_causation_id_must_be_uuid() -> None:
    """Чужой id в причинности не проходит: формат uuid, fail-closed."""
    with pytest.raises(EnvelopeError):
        make("act", "synapse", "ollama", TRACE, {}, Cost(), causation_id="вчерашнее-событие")


def test_journal_stamps_stored_at_at_append() -> None:
    """Момент записи знает журнал, не изготовитель: stored_at ставится при append."""
    journal = Journal()
    envelope = make("observe", "brainstem", "markitdown", TRACE, {}, Cost())
    assert "stored_at" not in envelope
    stored = journal.append(envelope)
    assert stored["stored_at"].endswith("Z")
    assert stored["stored_at"] >= stored["ts"]


def test_dedupe_tolerates_write_metadata() -> None:
    """stored_at/prev_id — метаданные файла, не эффект: dedupe их не считает конфликтом."""
    journal = Journal()
    envelope = make("act", "brainstem", "self", TRACE, {}, Cost(1, 1, 0.1))
    first = journal.append(envelope)
    second = journal.append(envelope)  # тот же id, тот же эффект — строка не дублируется
    assert second["id"] == first["id"]
    assert len(journal) == 1
    again = journal.append(first)  # возвращённый конверт уже несёт stored_at и prev_id
    assert again["id"] == first["id"]
    assert len(journal) == 1


def test_old_blood_without_origin_fields_stays_valid() -> None:
    """Схема аддитивна: кровь v0.4/v0.5 без полей происхождения валидна навсегда (п.6)."""
    envelope = make("act", "synapse", "ollama", TRACE, {"tool": "generate"}, Cost(10, 5, 0.5))
    validate(envelope)
    journal = Journal()
    stored = journal.append(envelope)
    assert "trust" not in stored
    assert "privacy" not in stored
    assert "occurred_at" not in stored


def test_spec_origin_example_validates() -> None:
    """Пример честного происхождения из SPEC-0003 валиден по схеме."""
    envelope = {
        "id": str(uuid.uuid4()),
        "ts": "2026-11-03T12:00:00Z",
        "stored_at": "2026-11-03T12:00:00Z",
        "occurred_at": "2026-11-03T09:30:00Z",
        "observed_at": "2026-11-03T11:59:59Z",
        "type": "observe",
        "source": "brainstem",
        "organ": "markitdown",
        "trace_id": "1a197679acaa11bd",
        "payload": {"file": "notes.md", "note": "файл видел stat'ом"},
        "cost": {"tokens_in": 0, "tokens_out": 0, "seconds": 0.1},
        "trust": "verified",
        "privacy": "personal",
    }
    validate(envelope)


def test_hematology_of_origin_blood(tmp_path) -> None:
    """Кровь с происхождением перечитывается гематологией: 0 skipped, 0 гэпов."""
    path = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.append(
        make(
            "observe", "brainstem", "markitdown", TRACE, {}, Cost(),
            occurred_at="2026-11-03T09:30:00Z",
            observed_at="2026-11-03T11:59:59Z",
            trust="verified", privacy="internal",
        )
    )
    parent = journal.all()[0]
    journal.append(
        make(
            "act", "synapse", "ollama", TRACE, {}, Cost(5, 5, 1.0),
            causation_id=parent["id"], trust="derived",
        )
    )
    journal.to_jsonl(path)
    reread = Journal.from_jsonl(path)
    assert len(reread) == 2
    assert reread.skipped == 0
    report = verify(path)
    assert report["gaps"] == []
    assert report["chained"] is True
