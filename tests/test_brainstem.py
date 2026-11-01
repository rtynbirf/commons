"""Приёмка SPEC-0001: ствол мозга — цикл, трассируемость G1, замена G2, бюджет G3."""

from __future__ import annotations

from blood.envelope import Cost, make
from brainstem import Budget

from .conftest import step  # noqa: TID252


def test_empty_plan_halts(loop, journal) -> None:
    assert loop.run([]) is False
    (halt,) = journal.by_type("halt")
    assert "пустой план" in halt["payload"]["reason"]


def test_task_completes_through_synapses(loop, journal) -> None:
    """DoD M1: задача выполнена целиком через синапсы; журнал полон."""
    assert loop.run([step(payload={"data": "задача"})]) is True
    trace_events = journal.by_trace(journal.all()[0]["trace_id"])
    types = [e["type"] for e in trace_events]
    assert types == ["plan", "act", "observe", "reflect"]
    assert all(e["cost"] is not None for e in trace_events)


def test_full_reconstruction_from_journal(loop, journal) -> None:
    """G1: по журналу сессия восстанавливается полностью — что делали и сколько стоило."""
    loop.run([step(intent="первое"), step(intent="второе")], trace_id="recon-1")
    events = journal.by_trace("recon-1")
    types = [e["type"] for e in events]
    assert types == ["plan", "act", "observe", "reflect", "plan", "act", "observe", "reflect"]
    plans = [e for e in events if e["type"] == "plan"]
    assert [p["payload"]["intent"] for p in plans] == ["первое", "второе"]
    spent = journal.totals("recon-1")
    assert spent.tokens_in > 0


def test_substitution_keeps_loop_untouched(loop, journal) -> None:
    """G2: мёртвый орган → замена из манифеста; цикл не меняется, задача выполнена."""
    assert loop.run([step(organ="dead-b", intent="работа при выключенном органе")]) is True
    assert journal.by_type("organ.replace")
    (reflect,) = journal.by_type("reflect")
    assert reflect["payload"]["satisfied"] is True


def test_failed_organ_halts_task(loop, journal) -> None:
    """Отказной режим SPEC-0001: орган упал, замены нет → REFLECT + HALT."""
    assert loop.run([step(organ="fallen-d", intent="упасть красиво")]) is False
    assert journal.by_type("error")
    (reflect,) = journal.by_type("reflect")
    assert reflect["payload"]["satisfied"] is False


def test_budget_exhaustion_halts(loop, journal) -> None:
    """G3: бюджет исчерпан → HALT с событием halt, второго шага нет."""
    # Искусственно раздуваем кровь до лимита перед циклом.
    for _ in range(3):
        journal.append(make("act", "synapse", "sense-a", "budget-1", {"tool": "echo"}, Cost(tokens_in=100, seconds=1.0)))
    budget = Budget(tokens_in=200, seconds=2.5)
    assert loop.run([step(), step()], trace_id="budget-1", budget=budget) is False
    (halt,) = journal.by_type("halt")
    assert "бюджет исчерпан" in halt["payload"]["reason"]
    assert halt["source"] == "brainstem"


def test_no_calls_bypass_synapses(loop, journal) -> None:
    """Второй закон: каждый вызов органа — событие act от источника synapse."""
    loop.run([step(), step()], trace_id="law2")
    acts = journal.by_type("act")
    assert len(acts) == 2
    assert all(e["source"] == "synapse" for e in acts)
    # Цикл эмитит только plan/observe/reflect/halt — активные вызовы только через шлюз.
    brainstem_events = [e for e in journal.by_trace("law2") if e["source"] == "brainstem"]
    assert all(e["type"] in {"plan", "observe", "reflect", "halt"} for e in brainstem_events)


def test_veto_stops_task(loop, journal) -> None:
    """SPEC-0001: инструмент не объявлен — действия нет, задача останавливается."""
    assert loop.run([step(tool="запрещённый-инструмент")]) is False
    (veto,) = journal.by_type("veto")
    (reflect,) = journal.by_type("reflect")
    assert veto["payload"]["tool"] == "запрещённый-инструмент"
    assert reflect["payload"]["satisfied"] is False
