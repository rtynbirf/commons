"""Приёмка волны №24 — внешний аварийный стоп (W-0033) и бюджет внимания (W-0025).

SPEC-0001 v0.6.0 п.8: трейс останавливается снаружи, между шагами, честным
контуром stop.requested (source pid1) → reflect → halt; сломанный нерв не
приписывает волю Человеку. SPEC-0001 G3 + SPEC-0003 v0.15.0 п.17: внимание —
четвёртый ресурс бюджета, считется в крови по фактам, fail-closed на чужой
класс. Время и стоп-каналы инъецируются — приёмки не спят.
"""

from __future__ import annotations

from typing import Any

import pytest

from blood.envelope import Cost, EnvelopeError, make
from brainstem import Budget, Loop, Step
from brainstem.silence import ANSWER_APPROVED, ApprovalRequest, await_approval


# --- оснастка -----------------------------------------------------------------


def approval_step(organ: str = "sense-a", intent: str = "трогать необратимое") -> Step:
    return Step(
        organ=organ,
        tool="echo",
        payload={"data": "x"},
        intent=intent,
        approval_window=0.2,
        approval_why="приёмка волны №24",
    )


def types_of(journal, trace_id: str | None = None) -> list[str]:
    events = journal.by_trace(trace_id) if trace_id else journal.all()
    return [e["type"] for e in events]


def trace_totals(journal, trace_id: str) -> Cost:
    return journal.totals(trace_id)


# --- W-0033: внешний аварийный стоп -------------------------------------------


def test_stop_before_first_step_halts_without_act(gateway, journal) -> None:
    """Стоп-файл уже стоит: первый шаг не исполняется, воля Человека — source pid1."""
    loop = Loop(gateway, journal, stop_check=lambda: "причина Человека")
    done = loop.run([approval_step()], trace_id="t-stop-first")
    assert done is False
    assert types_of(journal, "t-stop-first") == ["stop.requested", "reflect", "halt"]
    stop = journal.by_trace("t-stop-first")[0]
    assert stop["source"] == "pid1"  # воля Человека отличима от воли тела (ADR-0006)
    assert stop["payload"]["reason"] == "причина Человека"
    assert stop["cost"]["attention"] == 1  # поданный стоп — потраченное внимание
    assert stop["attention_class"] == "P0"  # остановка перед риском
    assert not [e for e in journal.by_trace("t-stop-first") if e["type"] == "act"]


def test_stop_between_steps_lets_previous_finish(gateway, journal) -> None:
    """Стоп между шагами: первый шаг честно завершён (act+observe+reflect), второй не начат."""
    calls = {"n": 0}

    def stop_after_first() -> str | None:
        calls["n"] += 1
        return None if calls["n"] <= 1 else "хватит"

    loop = Loop(gateway, journal, stop_check=stop_after_first, approval_channel=lambda q: ANSWER_APPROVED)
    done = loop.run([approval_step(), Step(organ="sense-a", tool="echo", payload={"data": "y"}, intent="второй шаг")], trace_id="t-stop-mid")
    assert done is False
    events = journal.by_trace("t-stop-mid")
    kinds = [e["type"] for e in events]
    # первый шаг: план, одобрение, акт, наблюдение, рефлексия; второй: стоп-контур без плана
    assert kinds == [
        "plan", "approval.requested", "approval.granted", "act", "observe", "reflect",
        "stop.requested", "reflect", "halt",
    ]
    assert sum(1 for e in events if e["type"] == "act") == 1
    halt = events[-1]
    assert halt["payload"]["at_step"] == 0  # стоп пришёл во время шага 1 — граница этого шага
    assert "хватит" in halt["payload"]["reason"]


def test_stop_older_than_budget(gateway, journal) -> None:
    """Аварийный стоп старше бюджета: причина — стоп, не «бюджет исчерпан»."""
    loop = Loop(
        gateway,
        journal,
        stop_check=lambda: "стоп важнее денег",
        )
    done = loop.run(
        [Step(organ="sense-a", tool="echo", payload={"data": "x"}, intent="шаг")],
        trace_id="t-stop-budget",
        budget=Budget(tokens_in=1),  # лимит заведомо будет исчерпан
    )
    assert done is False
    kinds = types_of(journal, "t-stop-budget")
    assert "stop.requested" in kinds
    assert "halt" in kinds
    halt = [e for e in journal.by_trace("t-stop-budget") if e["type"] == "halt"][0]
    assert "стоп важнее денег" in halt["payload"]["reason"]
    assert "бюджет" not in halt["payload"]["reason"]


def test_stop_channel_garbage_names_and_stops(gateway, journal) -> None:
    """Нечитаемый стоп-сигнал: воля НЕ приписывается Человеку, тело назвало и остановилось."""
    loop = Loop(gateway, journal, stop_check=lambda: 42)  # мусор вместо строки
    done = loop.run([Step(organ="sense-a", tool="echo", payload={"data": "x"}, intent="шаг")], trace_id="t-stop-garbage")
    assert done is False
    kinds = types_of(journal, "t-stop-garbage")
    assert kinds == ["error", "reflect", "halt"]
    assert "stop.requested" not in kinds  # мусор — не воля Человека
    error = journal.by_trace("t-stop-garbage")[0]
    assert error["source"] == "brainstem"
    assert "нечитаем" in error["payload"]["reason"]


def test_stop_channel_fallen_names_and_stops(gateway, journal) -> None:
    """Упавший стоп-канал: error-конверт + halt — сломанный нерв не управляет молча."""

    def broken() -> str:
        raise RuntimeError("нерв порван")

    loop = Loop(gateway, journal, stop_check=broken)
    done = loop.run([Step(organ="sense-a", tool="echo", payload={"data": "x"}, intent="шаг")], trace_id="t-stop-broken")
    assert done is False
    kinds = types_of(journal, "t-stop-broken")
    assert kinds == ["error", "reflect", "halt"]
    assert "нерв порван" in journal.by_trace("t-stop-broken")[0]["payload"]["reason"]


def test_stop_running_organ_finishes_named_boundary(gateway, journal) -> None:
    """Честная граница: живой вызов органа договаривает, стоп берёт следующую границу шагов."""
    def stop_after_organ() -> str | None:
        # нерв смотрит только на факты крови: акт уже случился — стоп на границе
        has_act = any(e["type"] == "act" for e in journal.by_trace("t-stop-organ"))
        return "стоп по границе" if has_act else None

    loop = Loop(gateway, journal, stop_check=stop_after_organ)
    plan = [Step(organ="sense-a", tool="echo", payload={"data": "x"}, intent="шаг 1")]
    done = loop.run(plan, trace_id="t-stop-organ")
    assert done is False
    events = journal.by_trace("t-stop-organ")
    kinds = [e["type"] for e in events]
    # орган доработал: акт и наблюдение в крови; следующий шаг не планировался
    assert "act" in kinds and "observe" in kinds
    assert kinds[-3:] == ["stop.requested", "reflect", "halt"]
    assert sum(1 for e in events if e["type"] == "plan") == 1


def test_stop_older_than_approval_question(gateway, journal) -> None:
    """Стоп старше вопроса: остановленный трейс не задаёт косметический вопрос об одобрении."""
    loop = Loop(gateway, journal, stop_check=lambda: "не спрашивай", approval_channel=lambda q: ANSWER_APPROVED)
    done = loop.run([approval_step()], trace_id="t-stop-approval")
    assert done is False
    kinds = types_of(journal, "t-stop-approval")
    assert kinds == ["stop.requested", "reflect", "halt"]
    assert not [e for e in journal.by_trace("t-stop-approval") if e["type"].startswith("approval.")]


def test_no_stop_checker_keeps_old_behaviour(gateway, journal) -> None:
    """Аддитивность: без стоп-канала цикл живёт как раньше."""
    loop = Loop(gateway, journal)
    done = loop.run([Step(organ="sense-a", tool="echo", payload={"data": "x"}, intent="шаг")], trace_id="t-nostop")
    assert done is True
    assert "halt" not in types_of(journal, "t-nostop")


def test_stopped_trace_reconstructs_complete(tmp_path, gateway) -> None:
    """G1: остановленный стопом трейс закрыт по-записанному и реконструируется из крови."""
    from blood.journal import Journal, verify
    from blood.resume import reconstruct

    path = tmp_path / "blood.jsonl"
    j = Journal()
    j.attach(path)
    loop = Loop(gateway, j, stop_check=lambda: "стоп-файл")
    loop.run([approval_step()], trace_id="t-recon")
    report = verify(path)
    assert report["gaps"] == []
    session = reconstruct(path, "t-recon")
    assert session["complete"] is True
    assert session["halts"], "halt пропал из реконструкции"
    assert "стоп-файл" in session["halts"][0]["reason"]


def test_file_stop_signal_reads_text(tmp_path) -> None:
    """Стоп-файл — текст как универсальный нерв (SPEC-0010): причина — первая строка."""
    from brainstem.stop import FileStopSignal

    signal = FileStopSignal(tmp_path / "STOP")
    assert signal() is None  # файла нет — тишина
    (tmp_path / "STOP").write_text("остановись, пожалуйста\nпока не поздно", encoding="utf-8")
    assert signal() == "остановись, пожалуйста"


def test_file_stop_signal_empty_file_has_named_default(tmp_path) -> None:
    """Пустой стоп-файл — не тишина: дефолтная причина названа, не выдумана."""
    from brainstem.stop import FileStopSignal

    (tmp_path / "STOP").write_text("", encoding="utf-8")
    signal = FileStopSignal(tmp_path / "STOP")
    reason = signal()
    assert reason is not None
    assert "стоп" in reason


def test_file_stop_signal_does_not_delete_human_words(tmp_path) -> None:
    """Тело не удаляет слова Человека: файл после чтения живёт (граница — названа)."""
    from brainstem.stop import FileStopSignal

    stop_path = tmp_path / "STOP"
    stop_path.write_text("стоп", encoding="utf-8")
    signal = FileStopSignal(stop_path)
    assert signal() == "стоп"
    assert stop_path.exists()
    assert signal() == "стоп"  # повторное чтение честно снова останавливает


# --- W-0025: бюджет внимания ----------------------------------------------------


def test_approval_question_carries_attention(journal) -> None:
    """Вопрос с окном — потраченное внимание: cost.attention = 1, класс P0."""
    await_approval(
        journal, "t-att",
        ApprovalRequest(what="demo.необратимое", window_s=0.1, why="приёмка"),
        lambda q: ANSWER_APPROVED,
        clock=lambda: 100.0,
    )
    asked = journal.by_trace("t-att")[0]
    assert asked["type"] == "approval.requested"
    assert asked["cost"]["attention"] == 1
    assert asked["attention_class"] == "P0"


def test_attention_visible_in_trace_totals(gateway, journal) -> None:
    """Кровь — истина: totals трейса с одобренным окном считает внимание."""
    loop = Loop(gateway, journal, approval_channel=lambda q: ANSWER_APPROVED)
    done = loop.run([approval_step()], trace_id="t-totals")
    assert done is True
    assert trace_totals(journal, "t-totals").attention == 1


def test_attention_budget_halts_before_next_question(gateway, journal) -> None:
    """Бюджет внимания исчерпан — halt ДО следующего вопроса: косметики нет."""
    loop = Loop(gateway, journal, approval_channel=lambda q: ANSWER_APPROVED)
    plan = [approval_step(intent="вопрос 1"), approval_step(intent="вопрос 2")]
    done = loop.run(plan, trace_id="t-att-budget", budget=Budget(attention=1))
    assert done is False
    asked = [e for e in journal.by_trace("t-att-budget") if e["type"] == "approval.requested"]
    assert len(asked) == 1, "второй вопрос был задан при исчерпанном бюджете внимания"
    halt = [e for e in journal.by_trace("t-att-budget") if e["type"] == "halt"][-1]
    assert "attention" in halt["payload"]["reason"]


def test_attention_budget_alerts_once(gateway, journal) -> None:
    """Порог внимания — один alert на трейс, трейс продолжается до исчерпания (грамматика G3)."""
    loop = Loop(gateway, journal, approval_channel=lambda q: ANSWER_APPROVED)
    plan = [approval_step(intent="вопрос 1"), Step(organ="sense-a", tool="echo", payload={"data": "y"}, intent="шаг 2")]
    done = loop.run(plan, trace_id="t-att-alert", budget=Budget(attention=2, alert_ratio=0.5))
    assert done is True
    alerts = [e for e in journal.by_trace("t-att-alert") if e["type"] == "alert"]
    assert len(alerts) == 1
    assert "attention" in alerts[0]["payload"]["reason"]


def test_attention_budget_exhausted_by_last_step_does_not_pass(gateway, journal) -> None:
    """Граница включена (грамматика W-0029): исчерпание внимания последним шагом — halt, не проход."""
    loop = Loop(gateway, journal, approval_channel=lambda q: ANSWER_APPROVED)
    done = loop.run([approval_step()], trace_id="t-att-last", budget=Budget(attention=1))
    assert done is False
    halt = [e for e in journal.by_trace("t-att-last") if e["type"] == "halt"][-1]
    assert "attention" in halt["payload"]["reason"]


# --- SPEC-0003 п.17: fail-closed на классе внимания ------------------------------


def test_attention_dictionary_is_single() -> None:
    """Словарь один, копий нет (как REVERSIBILITY_CLASSES)."""
    from blood.envelope import ATTENTION_CLASSES

    assert ATTENTION_CLASSES == ("P0", "P1", "P2", "P3")


def test_unknown_attention_class_fails_closed(journal) -> None:
    """Неизвестный класс внимания — EnvelopeError до крови (ADR-0014)."""
    with pytest.raises(EnvelopeError, match="класс"):
        make("plan", "brainstem", "self", "t-x", {}, Cost(attention=1), attention_class="P9")
    assert list(journal.all()) == []


def test_attention_without_class_fails_closed(journal) -> None:
    """Потраченное внимание без имени цели — витрина: fail-closed."""
    with pytest.raises(EnvelopeError, match="класс"):
        make("plan", "brainstem", "self", "t-x", {}, Cost(attention=1))


def test_class_without_attention_fails_closed(journal) -> None:
    """Имя цели без потраченного — обман: fail-closed."""
    with pytest.raises(EnvelopeError, match="класс внимания"):
        make("plan", "brainstem", "self", "t-x", {}, Cost(), attention_class="P0")


def test_negative_attention_fails_closed(journal) -> None:
    """Отрицательное внимание — не цена: fail-closed."""
    with pytest.raises(EnvelopeError):
        make("plan", "brainstem", "self", "t-x", {}, Cost(attention=-1))


def test_attention_with_class_passes_and_old_blood_valid(journal) -> None:
    """Аддитивность: новая кровь несёт attention+класс, старая кровь без поля валидна навсегда."""
    env = make("plan", "brainstem", "self", "t-ok", {}, Cost(attention=1), attention_class="P0")
    assert env["cost"]["attention"] == 1
    assert env["attention_class"] == "P0"
    # старая кровь: cost без attention — валидна (гематология)
    old = {
        "id": env["id"], "ts": env["ts"], "type": "plan", "source": "brainstem",
        "organ": "self", "trace_id": "t-old", "payload": {},
        "cost": {"tokens_in": 1, "tokens_out": 2, "seconds": 0.5},
    }
    from blood.envelope import validate

    validate(old)  # не роняется
    from_dict = Cost.from_dict(old["cost"])
    assert from_dict.attention == 0
