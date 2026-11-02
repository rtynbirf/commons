"""Приёмка A01 (Ф-0.2, SPEC-0003): повторный append не повторяет эффект.

Зерно пакета «Human Membrane» (волна №15, матрица A01): повторная доставка
того же события не создаёт второе. До волны №16 журнал крови принимал
дубликат `id` и дубликат `idempotency_key` молча — красный прогон волны
№16 обязан это поймать живьём, затем журнал учится честному dedupe.
"""

from __future__ import annotations

import pytest

from blood.envelope import Cost, EnvelopeError, make
from blood.journal import Journal, verify


def _env(trace_id: str = "dedupe-a01", **kw) -> dict:
    return make(
        event_type="act",
        source="brainstem",
        organ="self",
        trace_id=trace_id,
        payload={"step": "one"},
        cost=Cost(tokens_in=1, tokens_out=0, seconds=0.0),
        **kw,
    )


def test_repeat_same_id_no_second_effect(tmp_path) -> None:
    """Тот же конверт дважды — в крови одна строка, эффект один."""
    journal = Journal()
    journal.attach(tmp_path / "blood.jsonl")
    env = _env()
    first = journal.append(env)
    second = journal.append(env)
    assert second["id"] == first["id"]
    assert len(journal) == 1
    journal.close()
    lines = [
        line
        for line in (tmp_path / "blood.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == 1
    report = verify(tmp_path / "blood.jsonl")
    assert report["gaps"] == []
    assert report["events"] == 1


def test_repeat_idempotency_key_no_second_effect(tmp_path) -> None:
    """Тот же idempotency_key у разных конвертов — эффект первый, дубликат не пишется."""
    journal = Journal()
    journal.attach(tmp_path / "blood.jsonl")
    first = journal.append(_env(idempotency_key="op-42"))
    duplicate = journal.append(_env(idempotency_key="op-42"))  # другой id и ts
    assert duplicate["id"] == first["id"]
    assert len(journal) == 1
    journal.close()
    report = verify(tmp_path / "blood.jsonl")
    assert report["events"] == 1
    assert report["gaps"] == []


def test_same_id_different_payload_fails_closed(tmp_path) -> None:
    """Тот же id с другим содержанием — не dedupe, а конфликт: fail-closed."""
    journal = Journal()
    journal.attach(tmp_path / "blood.jsonl")
    env = _env()
    journal.append(env)
    impostor = dict(env)
    impostor["payload"] = {"step": "подмена"}
    with pytest.raises(EnvelopeError):
        journal.append(impostor)
    assert len(journal) == 1
    journal.close()


def test_fresh_ids_append_normally(tmp_path) -> None:
    """Разные конверты без ключа пишутся как раньше: цепочка без гэпов."""
    journal = Journal()
    journal.attach(tmp_path / "blood.jsonl")
    journal.append(_env())
    journal.append(_env())
    assert len(journal) == 2
    journal.close()
    report = verify(tmp_path / "blood.jsonl")
    assert report["events"] == 2
    assert report["chained"] is True
    assert report["gaps"] == []


def test_resume_rebuilds_dedupe_from_file(tmp_path) -> None:
    """Новая сессия (from_jsonl) помнит ключи и id пролитой крови."""
    path = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.attach(path)
    stored = journal.append(_env(idempotency_key="op-7"))
    journal.close()

    resumed = Journal.from_jsonl(path)
    duplicate = resumed.append(_env(idempotency_key="op-7"))
    assert duplicate["id"] == stored["id"]
    assert len(resumed) == 1
    fresh = resumed.append(_env(idempotency_key="op-8"))
    assert fresh["id"] != stored["id"]
    assert len(resumed) == 2
    resumed.close()


def test_schema_accepts_key_and_old_blood_stays_valid() -> None:
    """Ключ — опциональное поле: старая кровь (без ключа) валидна навсегда."""
    with_key = _env(idempotency_key="op-1")
    assert with_key["idempotency_key"] == "op-1"
    old = _env()
    assert "idempotency_key" not in old
