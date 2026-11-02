"""Углы dedupe (A01, SPEC-0003 п.9), которых нет в tests/test_blood_dedupe.py.

Контрольный забег волны №15 (стык волн): не дублирует их приёмки — добирает
грани, на которые их сюит не смотрит. Всё зелёное на принятой базе волны №16.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from blood.envelope import Cost, EnvelopeError, make, new_trace_id
from blood.journal import Journal

TRACE = new_trace_id()


def _event(**kw) -> dict:
    return make("act", "brainstem", "self", TRACE, {"шаг": 1}, Cost(1, 0, 0.0), **kw)


def test_key_scope_is_one_journal_not_one_trace(tmp_path: Path) -> None:
    """Скоуп ключа — журнал, не трейс: тот же ключ в другом trace дедупится.

    Намерение названо один раз для журнала; идемпотентность сильнее
    трассировки. Кому нужны копии по трейсам — тот называет ключи различно.
    """
    path = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.attach(path)
    journal.append(make("act", "brainstem", "self", "trace-A", {"шаг": 1}, idempotency_key="шаг-1"))
    journal.append(make("act", "brainstem", "self", "trace-B", {"шаг": 1}, idempotency_key="шаг-1"))
    assert len(journal) == 1


def test_distinct_keys_same_payload_both_stored(tmp_path: Path) -> None:
    """Ключ называет намерение, не содержимое: разные ключи — два конверта."""
    path = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.attach(path)
    journal.append(_event(idempotency_key="попытка-1"))
    journal.append(_event(idempotency_key="попытка-2"))
    assert len(journal) == 2


def test_same_key_different_payload_keeps_first(tmp_path: Path) -> None:
    """Повтор ключа с другим payload — дедуп: записанное не подменяется.

    Вторая доставка с тем же ключом возвращает ПЕРВЫЙ конверт с его
    собственным payload — поздний payload не переписывает пролитую кровь.
    """
    path = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.attach(path)
    first = journal.append(make("act", "brainstem", "self", TRACE, {"шаг": 1}, idempotency_key="шаг-1"))
    second = journal.append(make("act", "brainstem", "self", TRACE, {"шаг": 2}, idempotency_key="шаг-1"))
    assert second["id"] == first["id"]
    assert second["payload"] == {"шаг": 1}, "дедуп подменил содержимое записанного"
    assert len(journal) == 1
    assert journal.all()[0]["payload"] == {"шаг": 1}


def test_empty_key_rejected_by_schema() -> None:
    """Пустой ключ — кривой конверт: наружу не выходит (minLength 1)."""
    with pytest.raises(EnvelopeError):
        _event(idempotency_key="")


def test_make_carries_idempotency_key() -> None:
    """make() передаёт ключ в конверт, и он валиден схемой."""
    envelope = _event(idempotency_key="шаг-1")
    assert envelope["idempotency_key"] == "шаг-1"


def test_from_jsonl_then_append_dedupes(tmp_path: Path) -> None:
    """resume-путь (п.8 → п.9): from_jsonl помнит ключи — append дедупится.

    Сессия, восстановившаяся из крови, не повторяет эффекты пролитой крови.
    """
    path = tmp_path / "blood.jsonl"
    j1 = Journal()
    j1.attach(path)
    j1.append(_event(idempotency_key="шаг-1"))
    j1.close()

    j2 = Journal.from_jsonl(path)
    j2.attach(path)
    assert len(j2) == 1
    again = j2.append(_event(idempotency_key="шаг-1"))
    assert again["id"] == json.loads(path.read_text(encoding="utf-8").splitlines()[0])["id"]
    assert len(j2) == 1, "from_jsonl не передал память ключей — дедуп протух"
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1, "после from_jsonl повтор дописан в файл"
