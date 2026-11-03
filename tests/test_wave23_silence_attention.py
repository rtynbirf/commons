# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмки волны №23 (стык 0.42.1; семантика цены перевёрнута честно на стыке 0.48.2).

W-0032 (правило тишины) живёт контуром `brainstem/silence.py` — принят базой
стыка по дисциплине стыка волны №18; его приёмки — `tests/test_silence.py` (17).
Параллельная машина крови нашей линии (`brainstem/approval.py`) выметена на
стыке: её кровь (`runs/2026-11-03-wave23-silence-attention`) — вещественное
доказательство, валидна навсегда (гематология), читается метриками и дневником
наравне с контурной (оба диалекта).

W-0025 (зерно FR-09 пакета «Human Membrane»): внимание Человека — ресурс
организма, счёт только по фактам крови, скрытой телеметрии нет, неизмеримое =
UNKNOWN. Канон цены — их волна №24 (пришла в историю первой): каждый вопрос
контура — P0-прерывание с `cost.attention=1`; внимание всегда присутствует в
словаре цены (аддитивно, старая кровь без поля валидна навсегда); приоритетное
ценообразование нашей линии (`ApprovalRequest.priority`) выметено на стыке
0.48.2 как параллельная машина того же зерна — словарь приоритетов и
`should_ask` живут в `brainstem/attention.py` как политика вопросов.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from blood.envelope import Cost, make
from blood.journal import Journal
from brainstem import Budget, Loop, Step
from brainstem.attention import (
    ATTENTION_PRIORITIES,
    attention_cost,
    metrics,
    should_ask,
)
from brainstem.silence import ANSWER_APPROVED, ApprovalRequest, await_approval
from tests.test_silence import FakeClock, fake_sleep

from .conftest import step  # noqa: TID252


def _ts(shift_seconds: float = 0.0) -> str:
    """Момент для injected-времени: RFC 3339 с Z, как ставит журнал."""
    base = datetime(2026, 11, 3, 12, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(seconds=shift_seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


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
    # канон их волны №24: внимание — в словаре цены всегда (аддитивно,
    # старая кровь без поля валидна навсегда — граница, не прореха)
    assert Cost().as_dict() == {"tokens_in": 0, "tokens_out": 0, "seconds": 0.0, "attention": 0}
    assert Cost(attention=2).as_dict()["attention"] == 2
    envelope = make(
        "approval.request",
        "pid1",
        "self",
        "t1",
        {"what": "шаг"},
        Cost(attention=1),
        occurred_at=_ts(0),
        attention_class="P0",
    )
    assert envelope["cost"]["attention"] == 1
    assert Cost.from_dict({"tokens_in": 1, "tokens_out": 2, "seconds": 0.5}).attention == 0
    assert (Cost(attention=1) + Cost(attention=3)).attention == 4
    totals = Journal()
    totals.append(envelope)
    assert totals.totals("t1").attention == 1  # итоги трейса несут и внимание


def test_metrics_unknown_stays_unknown() -> None:
    report = metrics([], now=_ts(0))
    assert report["questions"] == 0
    assert report["wait_seconds_max"] is None  # неизмеримое = UNKNOWN, не ноль
    assert report["dismissed_fraction"] is None


# --- стык: метрики читают оба диалекта крови одобрения ---


def _historical_dialect(journal: Journal) -> None:
    """Кровь волны №23 нашей линии (диалект approval.request/grant) — свидетельство."""
    ask_a = make(
        "approval.request", "pid1", "self", "t1",
        {"what": "шаг-а", "window_seconds": 600, "expires_at": _ts(600)},
        Cost(attention=1), idempotency_key="hist:request:a", occurred_at=_ts(0), trust="unverified",
        attention_class="P0",
    )
    journal.append(ask_a)
    journal.append(make(
        "approval.grant", "pid1", "self", "t1",
        {"request_id": ask_a["id"], "who": "PID 1"},
        Cost(), idempotency_key="hist:grant:a", causation_id=ask_a["id"], occurred_at=_ts(30), trust="unverified",
    ))
    ask_b = make(
        "approval.request", "pid1", "self", "t1",
        {"what": "шаг-б", "window_seconds": 10, "expires_at": _ts(10)},
        Cost(attention=1), idempotency_key="hist:request:b", occurred_at=_ts(0), trust="unverified",
        attention_class="P0",
    )
    journal.append(ask_b)
    journal.append(make(
        "veto", "pid1", "self", "t1",
        {"request_id": ask_b["id"], "rule": "silence", "reason": "правило тишины: окно истекло без одобрения — по умолчанию «нет»"},
        Cost(), idempotency_key="hist:silence:b", causation_id=ask_b["id"], occurred_at=_ts(60), trust="verified",
    ))


def test_metrics_reads_historical_blood_of_our_line() -> None:
    journal = Journal()
    _historical_dialect(journal)
    journal.append(
        make("act", "brainstem", "self", "t1", {"tool": "drop", "reversibility": "irreversible"}, Cost(seconds=0.1))
    )
    report = metrics(journal.all(), now=_ts(70))
    assert report["questions"] == 2
    assert report["interruptions"] == 2  # обе заявки P0/P1 — cost.attention=1
    assert report["granted"] == 1
    assert report["cancelled_by_silence"] == 1
    assert report["refused"] == 0
    assert report["late_approvals"] == 0
    assert report["dangerous_actions"] == 1
    assert report["wait_seconds_max"] == pytest.approx(60.0)  # максимум: тишина ждала 0→60 с (granted — 30 с)
    assert report["dismissed_fraction"] == pytest.approx(0.5)
    # чистая функция: та же кровь — тот же отчёт, никакого скрытого состояния
    assert metrics(journal.all(), now=_ts(70)) == report


def test_metrics_reads_contour_blood() -> None:
    journal = Journal()
    clock = FakeClock()
    first = await_approval(
        journal, "t1",
        ApprovalRequest(what="demo.a", window_s=0.5, why="одобрено в окне"),
        lambda query: ANSWER_APPROVED, clock=clock, sleeper=fake_sleep(clock),
    )
    assert first == ANSWER_APPROVED
    verdict = await_approval(
        journal, "t1",
        ApprovalRequest(what="demo.b", window_s=0.3, why="канал молчит всё окно"),
        lambda query: None, clock=clock, sleeper=fake_sleep(clock),
    )
    assert verdict == "expired"
    report = metrics(journal.all())
    assert report["questions"] == 2
    assert report["interruptions"] == 2  # каждый вопрос — P0 с ценой 1 (канон их волны №24)
    assert report["granted"] == 1
    assert report["refused"] == 0
    assert report["cancelled_by_silence"] == 1
    assert report["late_approvals"] == 0  # контур одноразовый: опоздавших не бывает
    assert report["dismissed_fraction"] == pytest.approx(0.5)
    assert report["wait_seconds_max"] is not None and report["wait_seconds_max"] > 0  # заявленное waited_s
    assert metrics(journal.all()) == report


# --- зерно стыка: вопрос контура о необратимом — P0-цена ---


def test_contour_question_about_irreversible_costs_attention_p0(gateway: object, journal: Journal) -> None:
    loop = Loop(gateway, journal, approval_channel=lambda query: ANSWER_APPROVED)
    done = loop.run(
        [Step(organ="sense-a", tool="echo", payload={"key": "k", "value": "v"},
              intent="необратимое с окном", reversibility="irreversible", approval_window=0.5)],
        trace_id="t1",
        budget=Budget(),
    )
    assert done is True
    requested = [e for e in journal.by_type("approval.requested") if e["trace_id"] == "t1"]
    assert len(requested) == 1
    assert requested[0]["cost"]["attention"] == 1  # остановка и вопрос Человеку — заявленная цена (W-0025)
    acts = [e for e in journal.by_type("act") if e["trace_id"] == "t1"]
    assert len(acts) == 1 and acts[0]["payload"].get("reversibility") == "irreversible"


def test_contour_question_declares_p0_price_canonical(gateway: object, journal: Journal) -> None:
    """Канон их волны №24 (пришла в историю первой): каждый вопрос — P0 с ценой 1;
    приоритетное ценообразование нашей линии выметено на стыке 0.48.2."""
    loop = Loop(gateway, journal, approval_channel=lambda query: ANSWER_APPROVED)
    done = loop.run(
        [Step(organ="sense-a", tool="echo", payload={"data": "x"},
              intent="обратимое с окном", approval_window=0.5)],
        trace_id="t1",
        budget=Budget(),
    )
    assert done is True
    requested = [e for e in journal.by_type("approval.requested") if e["trace_id"] == "t1"]
    assert len(requested) == 1
    assert requested[0]["cost"]["attention"] == 1
    assert requested[0]["attention_class"] == "P0"


# --- стык: дневник говорит на обоих диалектах ---


def test_diary_speaks_both_dialects() -> None:
    from blood.diary import entries

    journal = Journal()
    clock = FakeClock()
    verdict = await_approval(
        journal, "t1",
        ApprovalRequest(what="удалить прод-таблицу", window_s=0.5, why="необратимое"),
        lambda query: ANSWER_APPROVED, clock=clock, sleeper=fake_sleep(clock),
    )
    assert verdict == ANSWER_APPROVED
    expired = await_approval(
        journal, "t1",
        ApprovalRequest(what="письмо наружу", window_s=0.2, why="канал молчит"),
        lambda query: None, clock=clock, sleeper=fake_sleep(clock),
    )
    assert expired == "expired"
    _historical_dialect(journal)  # кровь нашей линии — в том же доме
    report = entries(journal)
    results = [record["результат"] for record in report["records"]]
    assert any("вопрос Человеку" in result for result in results)  # оба диалекта вопроса в словаре дневника
    assert any("одобрил" in result for result in results)  # и оба диалекта одобрения
    assert any("тишина" in result for result in results)  # expired и veto правила названы отказом с причиной
    prices = [record["цена"] for record in report["records"] if "вопрос Человеку" in record["результат"]]
    assert prices and "внимание Человека 1" in prices[0]  # P0-вопрос несёт заявленную цену внимания


# --- стык (0.48.2): вето — остановка до факта без внимания (канон их волны №24:
# внимание несут вопрос контура и внешний стоп, не воля тела) ---


def test_loop_veto_stops_before_fact_without_attention(gateway: object, journal: Journal) -> None:
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
    assert vetoes[0]["cost"]["attention"] == 0  # вето — остановка, цену несёт вопрос (approval.requested)
    halts = [event for event in journal.by_type("halt") if event["trace_id"] == "t2"]
    assert halts and halts[0]["cost"]["attention"] == 0  # halt сам внимания не тратит
