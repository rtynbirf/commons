"""Честное происхождение: адаптер контракта пакета и конвенции чтения —
SPEC-0003 п.10 (такт 2 волны №17, W-0022).

Ядро тройного времени/классов служено тактом 1 (`tests/test_blood_origin.py`,
параллельный забег — база принята); этот сюит добирает стык: адаптер
контракта пакета «Human Membrane» (A02/A17 — тонкий слой перевода), конвенции
чтения `blood/provenance.py` (незаявленное не достраивается задним числом)
и совместимость с дедупом A01 на их семантике.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from blood.adapter import house_event_types, import_event
from blood.envelope import Cost, EnvelopeError, load_schema, make, validate
from blood.journal import Journal, verify
from blood.provenance import event_time, privacy_of, trust_of

TRACE = "provenance-t1"

# Событие контракта пакета «Human Membrane» (blood-event.schema.json v0.1.0).
MEMBRANE_EVENT: dict = {
    "event_id": "mem-e-1001",
    "event_name": "act",
    "schema_version": "0.1.0",
    "occurred_at": "2026-11-02T10:00:00Z",
    "observed_at": "2026-11-02T10:00:01Z",
    "stored_at": "2026-11-02T10:00:02Z",
    "source": "colleague",
    "organ": None,
    "trace_id": "mem-1",
    "correlation_id": "corr-1",
    "causation_id": "mem-cause-77",
    "sequence": 7,
    "payload": {"what": "external act"},
    "cost": {"tokens": 5, "duration_ms": 12},
    "trust": "verified",
    "privacy": "personal",
}


# --- незаявленное не выдумывается (конвенции чтения) ----------------------------


def test_undeclared_fields_are_not_fabricated() -> None:
    """Поле, о котором отправителю нечего сказать, не выдумывается (п.10)."""
    env = make("act", "brainstem", "self", TRACE, {})
    for field in ("occurred_at", "observed_at", "causation_id", "trust", "privacy"):
        assert field not in env
    validate(env)
    assert event_time(env) is None
    assert trust_of(env) == "unknown"
    assert privacy_of(env) == "sensitive"  # неклассифицированное наружу — sensitive


def test_declared_times_are_carried_in_order(tmp_path: Path) -> None:
    """Заявленное переносится; хронология честной записи соблюдается."""
    env = make(
        "act", "brainstem", "self", TRACE, {},
        occurred_at="2026-11-02T10:00:00Z",
        observed_at="2026-11-02T12:00:00Z",
    )
    assert env["occurred_at"] < env["observed_at"]
    journal = Journal()
    journal.attach(tmp_path / "blood.jsonl")
    stored = journal.append(env)
    assert stored["occurred_at"] < stored["observed_at"] <= stored["stored_at"]
    journal.close()


def test_unknown_fact_time_is_null_not_fabricated() -> None:
    """A02: неизвестное время остаётся UNKNOWN — явный null, не фиктивная отметка."""
    env = make("act", "brainstem", "self", TRACE, {}, occurred_at=None)
    assert env["occurred_at"] is None
    validate(env)
    assert event_time(env) is None


def test_fact_time_without_zone_fails_closed() -> None:
    """Время без зоны запись не проходит: мусорное время в кровь не попадает."""
    with pytest.raises(EnvelopeError):
        make("act", "brainstem", "self", TRACE, {}, occurred_at="2026-11-03T10:00:00")


def test_journal_stamps_stored_at(tmp_path: Path) -> None:
    """Момент записи знает журнал: отправитель stored_at не заявляет."""
    env = make("act", "brainstem", "self", TRACE, {})
    assert "stored_at" not in env
    journal = Journal()
    journal.attach(tmp_path / "blood.jsonl")
    stored = journal.append(env)
    assert stored["stored_at"] >= stored["ts"]
    assert "prev_id" not in stored  # первый конверт файла цепочку не несёт
    journal.close()


def test_sender_stored_at_claim_is_overwritten_by_journal(tmp_path: Path) -> None:
    """Заявка отправителя о записи перезаписывается честной (п.10)."""
    env = make("act", "brainstem", "self", TRACE, {})
    env["stored_at"] = "2020-01-01T00:00:00Z"
    journal = Journal()
    journal.attach(tmp_path / "blood.jsonl")
    stored = journal.append(env)
    assert stored["stored_at"] != "2020-01-01T00:00:00Z"
    assert stored["stored_at"] >= stored["ts"]


def test_dedupe_ignores_journal_fields(tmp_path: Path) -> None:
    """Повторный append того же конверта — dedupe и после stored_at (пп.9–10).

    Метаданные файла (prev_id, stored_at) не входят в сравнение содержания.
    """
    journal = Journal()
    journal.attach(tmp_path / "blood.jsonl")
    env = make("act", "brainstem", "self", TRACE, {"n": 1})
    first = journal.append(env)
    again = journal.append(env)
    assert again["id"] == first["id"]
    assert again["stored_at"] == first["stored_at"]
    assert len(journal) == 1


def test_same_id_other_content_is_conflict(tmp_path: Path) -> None:
    """Тот же id с другим содержанием — конфликт (fail-closed), не dedupe."""
    journal = Journal()
    journal.attach(tmp_path / "blood.jsonl")
    env = make("act", "brainstem", "self", TRACE, {"n": 1})
    journal.append(env)
    forged = dict(env)
    forged["payload"] = {"n": 2}
    with pytest.raises(EnvelopeError):
        journal.append(forged)


# --- классы доверия и приватности ------------------------------------------------


def test_trust_and_privacy_classes_are_carried() -> None:
    env = make(
        "act", "brainstem", "self", TRACE, {},
        trust="verified", privacy="personal",
    )
    assert env["trust"] == "verified"
    assert env["privacy"] == "personal"


def test_wrong_class_fails_closed() -> None:
    with pytest.raises(EnvelopeError):
        make("act", "brainstem", "self", TRACE, {}, trust="trusted")
    with pytest.raises(EnvelopeError):
        make("act", "brainstem", "self", TRACE, {}, privacy="secret")


def test_old_blood_reads_honestly() -> None:
    """Пролитая кровь v0.5 (без полей происхождения) валидна навсегда (п.6).

    Чтение честно и консервативно: доверие не заявлено — unknown (не
    достраиваем), классификация не заявлена — наружу sensitive
    (недоклассификация не облегчает режим), время факта — UNKNOWN.
    """
    old = {
        "id": str(uuid.uuid4()),
        "ts": "2026-11-02T12:00:00Z",
        "type": "act",
        "source": "brainstem",
        "organ": "self",
        "trace_id": "old-t",
        "payload": {},
        "cost": {"tokens_in": 0, "tokens_out": 0, "seconds": 0.0},
    }
    validate(old)
    assert event_time(old) is None
    assert trust_of(old) == "unknown"
    assert privacy_of(old) == "sensitive"


# --- причинность ------------------------------------------------------------------


def test_causation_id_links_semantic_parent() -> None:
    """Семантический родитель — uuid, не файловая цепочка prev_id."""
    cause = make("plan", "brainstem", "self", TRACE, {"index": 0})
    effect = make(
        "act", "brainstem", "self", TRACE, {"index": 0},
        causation_id=cause["id"],
    )
    assert effect["causation_id"] == cause["id"]
    assert "prev_id" not in cause


def test_causation_id_must_be_uuid() -> None:
    with pytest.raises(EnvelopeError):
        make("act", "brainstem", "self", TRACE, {}, causation_id="mem-cause-77")


# --- адаптер контракта пакета (blood/adapter.py) ----------------------------------


def test_house_event_types_come_from_schema() -> None:
    """Словарь типов адаптера — сама схема крови, копии в коде нет."""
    assert house_event_types() == frozenset(
        load_schema()["properties"]["type"]["enum"]
    )


def test_adapter_imports_known_event() -> None:
    env = import_event(dict(MEMBRANE_EVENT), trace_id="house-t", cost=Cost(0, 0, 1.5))
    assert env["type"] == "act"
    # заявленное время факта переносится; хронология честной записи видна
    assert env["occurred_at"] == "2026-11-02T10:00:00Z"
    # домовое observed_at — заявка адаптера о приёме, их наблюдение — провенанс
    assert "observed_at" in env
    assert env["observed_at"] != MEMBRANE_EVENT["observed_at"]
    assert env["occurred_at"] < env["observed_at"]
    assert env["trust"] == "verified"
    assert env["privacy"] == "personal"
    # волна №24 (W-0025): цена приёма несёт и внимание (ноль — не тратилось)
    assert env["cost"] == {"tokens_in": 0, "tokens_out": 0, "seconds": 1.5, "attention": 0}
    assert "stored_at" not in env  # их stored_at — не заявка дома
    assert "causation_id" not in env  # их causation_id — не uuid дома
    membrane = env["payload"]["membrane"]
    assert membrane["event_id"] == "mem-e-1001"
    assert membrane["observed_at"] == "2026-11-02T10:00:01Z"
    assert membrane["stored_at"] == "2026-11-02T10:00:02Z"
    assert membrane["causation_id"] == "mem-cause-77"
    assert membrane["sequence"] == 7
    assert membrane["correlation_id"] == "corr-1"
    assert membrane["cost"] == {"tokens": 5, "duration_ms": 12}
    validate(env)


def test_adapter_defaults_declare_nothing() -> None:
    """Незаявленное пакетом не выдумывается: null/без полей (чтение честно)."""
    env = import_event({"event_name": "observe"}, trace_id="house-t")
    assert env["occurred_at"] is None  # A02
    for field in ("trust", "privacy"):
        assert field not in env
    assert trust_of(env) == "unknown"
    assert privacy_of(env) == "sensitive"  # наружу — fail-closed
    assert event_time(env) is None
    membrane = env["payload"]["membrane"]
    assert membrane["contract"] == "human-membrane/blood-event"
    assert set(membrane) == {"contract"}


def test_adapter_unknown_event_saved_not_executed(tmp_path: Path) -> None:
    """A17: неизвестное событие сохраняется, не исполняется (ADR-0014).

    Знание уходит в error-конверт (оригинал в payload); чужой тип в крови
    не живёт ни строкой, ни памятью; журнал цел.
    """
    stranger = dict(MEMBRANE_EVENT, event_name="consciousness.surge")
    env = import_event(stranger, trace_id="house-t")
    assert env["type"] == "error"
    assert env["payload"]["original"]["event_name"] == "consciousness.surge"
    assert env["payload"]["event_name"] == "consciousness.surge"
    journal = Journal()
    journal.attach(tmp_path / "blood.jsonl")
    journal.append(env)
    journal.append(make("reflect", "brainstem", "self", "house-t", {"verdict": "незнакомое разобрано"}))
    assert len(journal) == 2  # сохранён
    assert journal.by_type("consciousness.surge") == ()  # не исполнен
    assert journal.by_type("error") != ()
    report = verify(tmp_path / "blood.jsonl")
    assert report["gaps"] == []
    assert report["chained"]
    journal.close()


def test_adapter_privacy_inherits_on_unknown_event() -> None:
    """Пришедшее personal/sensitive не понижается приёмом error-конверта."""
    stranger = dict(MEMBRANE_EVENT, event_name="weird.kind", privacy="sensitive")
    env = import_event(stranger, trace_id="house-t")
    assert env["type"] == "error"
    assert env["privacy"] == "sensitive"


def test_adapter_zoneless_time_fails_closed() -> None:
    stranger = dict(MEMBRANE_EVENT, occurred_at="2026-11-02T10:00:00")
    with pytest.raises(EnvelopeError):
        import_event(stranger, trace_id="house-t")


def test_adapter_rejects_non_object() -> None:
    with pytest.raises(EnvelopeError):
        import_event("событие строкой", trace_id="house-t")  # type: ignore[arg-type]
