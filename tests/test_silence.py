"""Приёмка правила тишины — W-0032 (SPEC-0004 v0.2.0 п.8, SPEC-0001 v0.4.0 п.5).

Тишина = «нет» по-записанному: окно → ответ Человека → дефолт; весь контур
виден в крови (approval.requested → granted | veto | expired), ни одного
немого ожидания. Время инъецируется — приёмки не спят.
"""

from __future__ import annotations

from typing import Any

import pytest

from brainstem import Step
from brainstem.silence import (
    ANSWER_APPROVED,
    ANSWER_EXPIRED,
    ANSWER_VETOED,
    ApprovalRequest,
    await_approval,
)


class FakeClock:
    """Инъекция времени: приёмки не спят, окно проживается прыжками."""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def fake_sleep(clock: FakeClock):
    """Сон для фейковых часов: засыпание = прыжок времени."""

    def _sleep(seconds: float) -> None:
        clock.advance(seconds)

    return _sleep


def request(window_s: float = 0.5, what: str = "demo.destructive", why: str = "тест") -> ApprovalRequest:
    return ApprovalRequest(what=what, window_s=window_s, why=why)


def approvals(journal) -> list[dict[str, Any]]:
    return [e for e in journal.all() if e["type"].startswith("approval.")]


# --- правило без окна — не правило -------------------------------------------


@pytest.mark.parametrize("window", [0, -1.0])
def test_rule_without_window_is_no_rule(journal, window: float) -> None:
    """Окно <= 0 — ValueError ДО первой записи: ничего не случилось."""
    with pytest.raises(ValueError, match="без окна"):
        await_approval(journal, "t1", request(window), lambda q: None, clock=FakeClock())
    assert len(journal.all()) == 0


def test_poll_interval_must_be_positive(journal) -> None:
    with pytest.raises(ValueError, match="poll_interval"):
        await_approval(journal, "t1", request(), lambda q: None, clock=FakeClock(), poll_interval=0)
    assert len(journal.all()) == 0


# --- тишина: окно истекло — отмена по-записанному ----------------------------


def test_silence_expires_to_cancel(journal) -> None:
    """Канал молчит всё окно → expired; конверты requested → expired; дефолт cancel."""
    clock = FakeClock()
    verdict = await_approval(
        journal, "t1", request(0.4), lambda q: None, clock=clock, sleeper=fake_sleep(clock)
    )
    assert verdict == ANSWER_EXPIRED
    types = [e["type"] for e in journal.by_trace("t1")]
    assert types == ["approval.requested", "approval.expired"]
    asked, expired = journal.by_trace("t1")
    assert asked["payload"]["what"] == "demo.destructive"
    assert asked["payload"]["default"] == "cancel"
    assert asked["source"] == "brainstem"
    assert expired["payload"]["reason"] == "silence"
    assert expired["payload"]["default"] == "cancel"
    assert expired["payload"]["waited_s"] >= 0.35


def test_late_answer_after_window_is_still_silence(journal) -> None:
    """Ответ, пришедший после истечения окна, не отменяет принятого решения."""
    clock = FakeClock()

    def late(query: dict) -> str | None:
        return "approved" if clock() >= 100.4 else None

    verdict = await_approval(journal, "t1", request(0.4), late, clock=clock, sleeper=fake_sleep(clock))
    assert verdict == ANSWER_EXPIRED
    assert [e["type"] for e in approvals(journal)] == ["approval.requested", "approval.expired"]
    assert not journal.by_type("approval.granted")


# --- ответ Человека: одобрение и вето ----------------------------------------


def test_approval_within_window(journal) -> None:
    """Одобрение в окне → granted; воля Человека пишется источником pid1."""
    clock = FakeClock()
    verdict = await_approval(
        journal, "t1", request(0.5), lambda q: ANSWER_APPROVED, clock=clock, sleeper=fake_sleep(clock)
    )
    assert verdict == ANSWER_APPROVED
    asked, granted = journal.by_trace("t1")
    assert asked["type"] == "approval.requested"
    assert granted["type"] == "approval.granted"
    assert granted["source"] == "pid1"
    assert granted["payload"]["answer"] == "approved"
    assert granted["payload"]["waited_s"] < 0.5


def test_veto_within_window(journal) -> None:
    """Вето Человека в окне → veto, source pid1; воля отличима от воли тела."""
    clock = FakeClock()
    verdict = await_approval(
        journal, "t1", request(0.5), lambda q: "vetoed", clock=clock, sleeper=fake_sleep(clock)
    )
    assert verdict == ANSWER_VETOED
    _, veto = journal.by_trace("t1")
    assert veto["type"] == "approval.veto"
    assert veto["source"] == "pid1"


# --- сломанный и мусорный канал: fail-closed ---------------------------------


def test_broken_channel_named_once_then_silence(journal) -> None:
    """Канал падает: один error-конверт, дальше тишина до конца окна → expired."""
    clock = FakeClock()

    def broken(query: dict) -> str | None:
        raise RuntimeError("нерв порван")

    verdict = await_approval(journal, "t1", request(0.3), broken, clock=clock, sleeper=fake_sleep(clock))
    assert verdict == ANSWER_EXPIRED
    types = [e["type"] for e in journal.by_trace("t1")]
    assert types == ["approval.requested", "error", "approval.expired"]
    (error,) = journal.by_type("error")
    assert "канал одобрения упал" in error["payload"]["reason"]


def test_garbage_answer_is_named_and_counts_as_silence(journal) -> None:
    """Мусорный ответ — не воля Человека: error-конверт, трактовка тишина."""
    clock = FakeClock()
    verdict = await_approval(
        journal, "t1", request(0.3), lambda q: "да ладно, живи", clock=clock, sleeper=fake_sleep(clock)
    )
    assert verdict == ANSWER_EXPIRED
    types = [e["type"] for e in journal.by_trace("t1")]
    assert types == ["approval.requested", "error", "approval.expired"]
    (error,) = journal.by_type("error")
    assert "мусор" in error["payload"]["reason"]


def test_channel_recovers_after_one_failure(journal) -> None:
    """Канал упал один раз и ожил: сбой назван, одобрение принято честно."""
    clock = FakeClock()
    state = {"calls": 0}

    def flaky(query: dict) -> str | None:
        state["calls"] += 1
        if state["calls"] == 1:
            raise IOError("дрогнул")
        return ANSWER_APPROVED

    verdict = await_approval(journal, "t1", request(0.5), flaky, clock=clock, sleeper=fake_sleep(clock))
    assert verdict == ANSWER_APPROVED
    types = [e["type"] for e in journal.by_trace("t1")]
    assert types == ["approval.requested", "error", "approval.granted"]


def test_channel_sees_question_and_left_time(journal) -> None:
    """Канал получает что/зачем/остаток окна — отвечает осмысленно, а не вслепую."""
    clock = FakeClock()
    seen: list[dict] = []

    def watcher(query: dict) -> str | None:
        seen.append(dict(query))
        return "vetoed"

    await_approval(journal, "t1", request(0.4, what="demo.wipe", why="стереть кэш"), watcher, clock=clock, sleeper=fake_sleep(clock))
    assert seen[0]["what"] == "demo.wipe"
    assert seen[0]["why"] == "стереть кэш"
    assert 0 < seen[0]["seconds_left"] <= 0.4


# --- интеграция цикла: шаг не доходит до органа без одобрения -----------------


def test_loop_expired_silence_halts_before_organ(loop, journal) -> None:
    """Тишина за окно: approval.expired → reflect → halt; до органа шаг не дошёл."""
    clock = FakeClock()
    loop.approval_channel = lambda q: None
    loop.clock = clock
    loop.sleeper = fake_sleep(clock)
    step = Step(
        organ="sense-a", tool="echo", payload={"data": "необратимое"},
        intent="трогать мир без спроса", approval_window=0.4,
    )
    assert loop.run([step], trace_id="sil-1") is False
    types = [e["type"] for e in journal.by_trace("sil-1")]
    assert types == ["plan", "approval.requested", "approval.expired", "reflect", "halt"]
    assert not journal.by_type("act")  # эффект НЕ состоялся
    (halt,) = journal.by_type("halt")
    assert "одобрение не получено" in halt["payload"]["reason"]
    (reflect,) = journal.by_type("reflect")
    assert reflect["payload"]["satisfied"] is False
    assert reflect["payload"]["reason"] == "approval: expired"


def test_loop_approved_step_proceeds(loop, journal) -> None:
    """Одобрение в окне: granted → act → observe → reflect; план исполнен."""
    loop.approval_channel = lambda q: "approved"
    step = Step(organ="sense-a", tool="echo", payload={"data": "поЗволено"},
                intent="трогать мир с разрешения", approval_window=1.0)
    assert loop.run([step], trace_id="sil-2") is True
    types = [e["type"] for e in journal.by_trace("sil-2")]
    assert types == ["plan", "approval.requested", "approval.granted", "act", "observe", "reflect"]
    (granted,) = journal.by_type("approval.granted")
    assert granted["source"] == "pid1"


def test_loop_veto_halts_before_organ(loop, journal) -> None:
    """Вето Человека: approval.veto → halt; до органа шаг не дошёл."""
    loop.approval_channel = lambda q: "vetoed"
    step = Step(organ="sense-a", tool="echo", payload={"data": "ветоed"},
                intent="попытка без разрешения", approval_window=1.0)
    assert loop.run([step], trace_id="sil-3") is False
    types = [e["type"] for e in journal.by_trace("sil-3")]
    assert types == ["plan", "approval.requested", "approval.veto", "reflect", "halt"]
    assert not journal.by_type("act")


def test_loop_without_channel_fails_closed_without_pretence(loop, journal) -> None:
    """Канал не подключён, а шаг требует окна: error + halt, БЕЗ притворного ожидания."""
    step = Step(organ="sense-a", tool="echo", payload={"data": "х"},
                intent="без нерва к Человеку", approval_window=1.0)
    assert loop.run([step], trace_id="sil-4") is False
    types = [e["type"] for e in journal.by_trace("sil-4")]
    assert types == ["plan", "error", "reflect", "halt"]
    assert approvals(journal) == []  # никакого approval.requested — ожидания не было
    (halt,) = journal.by_type("halt")
    assert "канал одобрения не подключён" in halt["payload"]["reason"]


def test_loop_rejects_rule_without_window(loop, journal) -> None:
    """Окно <= 0 в плане — дефект плана: ValueError, кровь чиста от approval.*."""
    loop.approval_channel = lambda q: None
    step = Step(organ="sense-a", tool="echo", payload={"data": "х"},
                intent="без окна", approval_window=0)
    with pytest.raises(ValueError, match="без окна"):
        loop.run([step], trace_id="sil-5")
    assert approvals(journal) == []


# --- кровь: конверты валидны по схеме, G1 трассируемость ----------------------


def test_approval_envelopes_carry_trace_and_cost(journal) -> None:
    """Каждый конверт контура несёт trace_id и цену (SPEC-0003: событие без цены не существует)."""
    clock = FakeClock()
    await_approval(
        journal, "trace-sil", request(0.3), lambda q: None, clock=clock, sleeper=fake_sleep(clock)
    )
    events = journal.by_trace("trace-sil")
    assert len(events) == 2
    for envelope in events:
        assert envelope["trace_id"] == "trace-sil"
        assert envelope["cost"] == {"tokens_in": 0, "tokens_out": 0, "seconds": 0.0}
        assert envelope["organ"] == "self"
