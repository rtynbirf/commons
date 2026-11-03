# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмки волны №23 — правило тишины и бюджет внимания человека (W-0032 + W-0025).

W-0032 (SPEC-0004 v0.2.0 п.8, поверх ADR-0006): у тишины есть записанное окно
и поведение по умолчанию — необратимое действие, по которому одобрение не
пришло за окно, отменяется по-записанному (veto от правила, не от Человека),
а не ждёт вечно. Запрос одобрения — событие крови с ЗАЯВЛЕННЫМ окном: запроса
без окна не существует (fail-closed, ADR-0014).

W-0025 (SPEC-0004 v0.2.0 п.9, зерно FR-09 пакета «Human Membrane»): внимание
Человека — ресурс организма: прерывания и вопросы учтены в цене события
(`cost.attention` рядом с токенами и секундами), политика P0–P3, косметические
вопросы с безопасным default не задаются, скрытой поведенческой телеметрии
нет — счёт только по заявленной крови, неизмеримое = UNKNOWN.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from blood.envelope import Cost, make
from blood.journal import Journal
from brainstem import Budget, Loop, Step
from brainstem.approval import (
    CANCELLED_BY_SILENCE,
    GRANTED,
    WAITING,
    answer,
    grant,
    pending,
    request,
)
from brainstem.attention import (
    ATTENTION_PRIORITIES,
    attention_cost,
    metrics,
    should_ask,
)
from synapse.gateway import Gateway

from .conftest import step  # noqa: TID252


def _ts(shift_seconds: float = 0.0) -> str:
    """Момент для injected-времени: RFC 3339 с Z, как ставит журнал."""
    base = datetime(2026, 11, 3, 12, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(seconds=shift_seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


# --- W-0032: запрос одобрения — грамматика с окном, fail-closed ---


def test_request_records_window_priority_and_attention() -> None:
    journal = Journal()
    envelope = request(
        journal,
        what="удалить прод-таблицу",
        window_seconds=3600,
        priority="P0",
        trace_id="t1",
        now=_ts(0),
    )
    stored = journal.by_type("approval.request")
    assert len(stored) == 1
    assert stored[0]["payload"]["what"] == "удалить прод-таблицу"
    assert stored[0]["payload"]["window_seconds"] == 3600
    assert stored[0]["payload"]["priority"] == "P0"
    assert stored[0]["payload"]["expires_at"] == _ts(3600)
    assert stored[0]["source"] == "pid1"
    assert stored[0]["cost"]["attention"] == 1  # P0 — прерывание Человека
    assert envelope["id"] == stored[0]["id"]


@pytest.mark.parametrize("window", [None, 0, -5])
def test_request_without_window_fail_closed(window: int | None) -> None:
    journal = Journal()
    with pytest.raises(ValueError):
        request(
            journal,
            what="шаг",
            window_seconds=window,  # type: ignore[arg-type]
            priority="P0",
            trace_id="t1",
            now=_ts(0),
        )
    assert len(journal.all()) == 0  # конверта нет — события не существует


def test_request_bad_priority_fail_closed() -> None:
    journal = Journal()
    with pytest.raises(ValueError):
        request(
            journal,
            what="шаг",
            window_seconds=60,
            priority="P9",  # не из словаря — не грамматика (ADR-0014)
            trace_id="t1",
            now=_ts(0),
        )
    assert len(journal.all()) == 0


def test_request_retry_is_deduped_a01() -> None:
    journal = Journal()
    first = request(journal, what="шаг", window_seconds=60, priority="P0", trace_id="t1", now=_ts(0))
    second = request(journal, what="шаг", window_seconds=60, priority="P0", trace_id="t1", now=_ts(5))
    assert first["id"] == second["id"]
    assert len(journal.by_type("approval.request")) == 1  # повторная заявка — одно событие


# --- W-0032: ответ — грант до окна, тишина за окном, ожидание до окна ---


def test_grant_before_expiry_is_recorded_with_causation() -> None:
    journal = Journal()
    ask = request(journal, what="шаг", window_seconds=600, priority="P0", trace_id="t1", now=_ts(0))
    give = grant(journal, ask, who="PID 1", trace_id="t1", now=_ts(60))
    assert give["type"] == "approval.grant"
    assert give["payload"]["request_id"] == ask["id"]
    assert give["payload"]["who"] == "PID 1"
    assert give["causation_id"] == ask["id"]  # честное происхождение (SPEC-0003 п.10)
    verdict, envelope = answer(journal, ask, now=_ts(120))
    assert verdict == GRANTED
    assert envelope is not None and envelope["type"] == "approval.grant"


def test_grant_retry_is_deduped_a01() -> None:
    journal = Journal()
    ask = request(journal, what="шаг", window_seconds=600, priority="P0", trace_id="t1", now=_ts(0))
    first = grant(journal, ask, who="PID 1", trace_id="t1", now=_ts(60))
    second = grant(journal, ask, who="PID 1", trace_id="t1", now=_ts(90))
    assert first["id"] == second["id"]
    assert len(journal.by_type("approval.grant")) == 1


def test_answer_waiting_before_expiry() -> None:
    journal = Journal()
    ask = request(journal, what="шаг", window_seconds=600, priority="P0", trace_id="t1", now=_ts(0))
    verdict, envelope = answer(journal, ask, now=_ts(120))
    assert verdict == WAITING
    assert envelope is None
    assert journal.by_type("veto") == ()  # ожидание ничего не пишет и ничего не отменяет


def test_silence_cancels_after_window_by_record() -> None:
    journal = Journal()
    ask = request(journal, what="шаг", window_seconds=600, priority="P0", trace_id="t1", now=_ts(0))
    verdict, envelope = answer(journal, ask, now=_ts(601))
    assert verdict == CANCELLED_BY_SILENCE
    assert envelope is not None and envelope["type"] == "veto"
    assert envelope["payload"]["request_id"] == ask["id"]
    assert "тишины" in envelope["payload"]["reason"]
    assert envelope["source"] == "pid1"  # отмена правилом дома, не чужой голос
    vetoes = journal.by_type("veto")
    assert len(vetoes) == 1


def test_silence_answer_is_idempotent_a01() -> None:
    journal = Journal()
    ask = request(journal, what="шаг", window_seconds=600, priority="P0", trace_id="t1", now=_ts(0))
    first_verdict, first = answer(journal, ask, now=_ts(601))
    second_verdict, second = answer(journal, ask, now=_ts(700))
    assert first_verdict == second_verdict == CANCELLED_BY_SILENCE
    assert first is not None and second is not None
    assert first["id"] == second["id"]
    assert len(journal.by_type("veto")) == 1  # повторное правило не пишет вторую строку


def test_late_grant_does_not_revive_cancelled() -> None:
    journal = Journal()
    ask = request(journal, what="шаг", window_seconds=600, priority="P0", trace_id="t1", now=_ts(0))
    verdict_before, _ = answer(journal, ask, now=_ts(601))
    assert verdict_before == CANCELLED_BY_SILENCE
    give = grant(journal, ask, who="PID 1", trace_id="t1", now=_ts(900))
    assert give["type"] == "approval.grant"  # весть записана — кровь append-only
    verdict_after, envelope = answer(journal, ask, now=_ts(950))
    assert verdict_after == CANCELLED_BY_SILENCE  # опоздавшее «да» не исполняет необратимое
    assert envelope is not None and envelope["type"] == "veto"


def test_pending_lists_only_unanswered() -> None:
    journal = Journal()
    given = request(journal, what="шаг-а", window_seconds=600, priority="P0", trace_id="t1", now=_ts(0))
    expired = request(journal, what="шаг-б", window_seconds=10, priority="P1", trace_id="t1", now=_ts(0))
    waiting = request(journal, what="шаг-в", window_seconds=600, priority="P1", trace_id="t1", now=_ts(0))
    grant(journal, given, who="PID 1", trace_id="t1", now=_ts(30))
    answer(journal, expired, now=_ts(60))
    left = pending(journal, now=_ts(60))
    assert [item["id"] for item in left] == [waiting["id"]]


# --- W-0025: словарь внимания, цена и политика вопросов ---


def test_attention_vocabulary_and_cost() -> None:
    assert ATTENTION_PRIORITIES == ("P0", "P1", "P2", "P3")
    assert attention_cost("P0") == 1  # остановка перед риском — прерывание
    assert attention_cost("P1") == 1  # срочное существенное — прерывание
    assert attention_cost("P2") == 0  # дневная сводка — Человек читает сам
    assert attention_cost("P3") == 0  # тихая запись — прерывания нет
    with pytest.raises(ValueError):
        attention_cost("P5")


def test_should_ask_policy_p0_to_p3() -> None:
    # P0 — остановка перед риском: спрашивает всегда, безопасного default у риска нет
    assert should_ask("P0", safe_default=True)[0] is True
    assert should_ask("P0", safe_default=False)[0] is True
    # P1 — срочное существенное: спрашивает, только если нет безопасного default
    assert should_ask("P1", safe_default=False)[0] is True
    assert should_ask("P1", safe_default=True)[0] is False  # косметический вопрос не задаётся
    # P2/P3 — сводка и тихая запись: не прерывают никогда
    assert should_ask("P2", safe_default=False)[0] is False
    assert should_ask("P3", safe_default=False)[0] is False
    for priority in ATTENTION_PRIORITIES:
        assert should_ask(priority, safe_default=False)[1]  # причина названа словами


def test_cost_attention_roundtrip_and_old_blood() -> None:
    # цена аддитивна: 0 не пишется (старый стиль жив), заявленное пишется
    assert Cost().as_dict() == {"tokens_in": 0, "tokens_out": 0, "seconds": 0.0}
    assert Cost(attention=2).as_dict()["attention"] == 2
    envelope = make(
        "approval.request",
        "pid1",
        "self",
        "t1",
        {"what": "шаг"},
        Cost(attention=1),
        occurred_at=_ts(0),
    )
    assert envelope["cost"]["attention"] == 1
    assert Cost.from_dict({"tokens_in": 1, "tokens_out": 2, "seconds": 0.5}).attention == 0
    assert (Cost(attention=1) + Cost(attention=3)).attention == 4
    totals = Journal()
    totals.append(envelope)
    assert totals.totals("t1").attention == 1  # итоги трейса несут и внимание


def test_metrics_count_only_declared_blood() -> None:
    journal = Journal()
    given = request(journal, what="шаг-а", window_seconds=600, priority="P0", trace_id="t1", now=_ts(0))
    expired = request(journal, what="шаг-б", window_seconds=10, priority="P1", trace_id="t1", now=_ts(0))
    grant(journal, given, who="PID 1", trace_id="t1", now=_ts(30))
    answer(journal, expired, now=_ts(60))
    journal.append(
        make("act", "brainstem", "self", "t1", {"tool": "drop", "reversibility": "irreversible"}, Cost(seconds=0.1))
    )
    report = metrics(journal.all(), now=_ts(70))
    assert report["questions"] == 2
    assert report["interruptions"] == 2  # обе заявки P0/P1 — cost.attention=1
    assert report["granted"] == 1
    assert report["cancelled_by_silence"] == 1
    assert report["refused"] == 0
    assert report["dangerous_actions"] == 1
    assert report["wait_seconds_max"] == pytest.approx(60.0)  # максимум: тишина ждала 0→60 с (granted — 30 с)
    assert report["dismissed_fraction"] == pytest.approx(0.5)
    # чистая функция: та же кровь — тот же отчёт, никакого скрытого состояния
    assert metrics(journal.all(), now=_ts(70)) == report


def test_metrics_unknown_stays_unknown() -> None:
    report = metrics([], now=_ts(0))
    assert report["questions"] == 0
    assert report["wait_seconds_max"] is None  # неизмеримое = UNKNOWN, не ноль
    assert report["dismissed_fraction"] is None


# --- стык волн: ствол и дневник говорят по-новому ---


def test_loop_veto_consumes_attention_p0(gateway: Gateway, journal: Journal) -> None:
    loop = Loop(gateway, journal)
    ok = loop.run([step(organ="sense-a", tool="echo")], trace_id="t1", budget=Budget())
    assert ok is True
    irreversible = Loop(gateway, journal)
    done = irreversible.run(
        [Step(organ="sense-a", tool="echo", payload={"key": "k", "value": "v"}, intent="необратимое", reversibility="irreversible")],
        trace_id="t2",
        budget=Budget(),
    )
    assert done is False
    vetoes = [event for event in journal.by_type("veto") if event["trace_id"] == "t2"]
    assert len(vetoes) == 1
    assert vetoes[0]["cost"]["attention"] == 1  # остановка и вопрос Человеку — P0-цена
    halts = [event for event in journal.by_type("halt") if event["trace_id"] == "t2"]
    assert halts and "attention" not in halts[0]["cost"]  # halt сам внимания не тратит


def test_diary_speaks_approvals() -> None:
    from blood.diary import entries

    journal = Journal()
    ask = request(journal, what="удалить прод-таблицу", window_seconds=600, priority="P0", trace_id="t1", now=_ts(0))
    grant(journal, ask, who="PID 1", trace_id="t1", now=_ts(30))
    expired = request(journal, what="письмо наружу", window_seconds=10, priority="P1", trace_id="t1", now=_ts(0))
    answer(journal, expired, now=_ts(20))
    report = entries(journal)
    results = [record["результат"] for record in report["records"]]
    assert any("вопрос Человеку" in result for result in results)  # словарь дневника знает approval.request
    assert any("одобрил" in result for result in results)  # и approval.grant
    assert any("тишины" in result for result in results)  # veto правила назван отказом с причиной
    prices = [record["цена"] for record in report["records"] if "вопрос Человеку" in record["результат"]]
    assert prices and "внимание Человека 1" in prices[0]  # P0-вопрос несёт заявленную цену внимания
