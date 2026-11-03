# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмки волны №22 — бюджет после шага и обратимость честным языком (W-0029 + W-0024).

W-0029 (SPEC-0001 v0.4.0 G3, зерно коллег F-07): бюджет проверяется не только
ПЕРЕД шагом, но и ПОСЛЕ — перерасход последним шагом завершает трейс halt,
а не проходом (run() = False).

W-0024 (SPEC-0001 v0.4.0 пп.5–6, SPEC-0003 v0.13.0 п.16, зерно FR-05/FR-06 и
ADR-002 пакета «Human Membrane» — Saga): шаг заявляет класс обратимости до
факта; необратимое без одобрения — veto до факта; отмена — новая операция-
компенсация с идемпотентным ключом и проверкой состояния после; вердикты
COMPENSATED / COMPENSATION_PARTIAL (не PASS) / NOT_REVERSIBLE; необратимое
честно не отменяется.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest
import yaml

from blood.envelope import REVERSIBILITY_CLASSES
from blood.journal import Journal
from brainstem import Budget, Loop, Step
from brainstem.compensator import (
    COMPENSATED,
    COMPENSATION_PARTIAL,
    NOT_REVERSIBLE,
    compensate,
)
from synapse.gateway import Gateway, SynapseVeto

from .conftest import MANIFEST, step  # noqa: TID252


class FakeStateful:
    """Орган с состоянием и компенсатором: `t` пишет ключ, `t_undo` откатывает.

    Компенсатор объявляется манифестом (`compensators: {t: t_undo}`) — данные,
    не код (G2). Инструмент отмены честно заявляет исход в результате:
    {"compensation": "full" | "partial", "state": снимок} — частичность
    заявляет орган, дом не догадывается.
    """

    def __init__(self, entry: dict[str, Any]) -> None:
        self.entry = entry
        self.state: dict[str, Any] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def health(self) -> bool:
        return True

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Any]:
        from blood.envelope import Cost

        self.calls.append((tool, payload))
        if tool == "t":
            self.state[payload["key"]] = payload["value"]
            return {"written": payload["key"]}, Cost(tokens_in=10, tokens_out=1, seconds=0.01)
        if tool == "t_undo":
            had = self.state.pop(payload["key"], None)
            if had is not None and payload.get("compensation_mode") == "partial":
                # откатил не всё: честная заявка частичности + остаток в состоянии
                self.state[f"{payload['key']}#остаток"] = "не откатилось"
                return {"compensation": "partial", "state": dict(self.state)}, Cost(tokens_in=10, tokens_out=1, seconds=0.01)
            return {"compensation": "full", "state": dict(self.state)}, Cost(tokens_in=10, tokens_out=1, seconds=0.01)
        raise AssertionError(f"неизвестный инструмент {tool}")


def _stateful_manifest(tmp_path: Path) -> Path:
    """Манифест общего вида + орган stateful (t/t_undo, компенсатор объявлен)."""
    organs = [dict(organ) for organ in MANIFEST["organs"]]
    organs.append(
        {
            "name": "stateful",
            "system": "effectors",
            "mode": "dependency",
            "upstream": "https://example.invalid/stateful",
            "license": "MIT",
            "transport": "stdio",
            "command": "fake-stateful",
            "healthcheck": "initialize handshake",
            "tools": ["t", "t_undo"],
            "authority": {"fs": "none", "network": "none"},
            "adapter": "tests.test_wave22_reversibility_budget:FakeStateful",
            "compensators": {"t": "t_undo"},
        }
    )
    path = tmp_path / "mcp-manifest.yaml"
    path.write_text(yaml.safe_dump({**MANIFEST, "organs": organs}, allow_unicode=True), encoding="utf-8")
    return path


@pytest.fixture()
def sloop(tmp_path: Path) -> tuple[Loop, Journal, Gateway]:
    journal = Journal()
    gateway = Gateway(_stateful_manifest(tmp_path), journal)
    return Loop(gateway, journal), journal, gateway


FULL = lambda r: r.get("compensation") == "full"  # noqa: E731 — критерий приёмки компенсации


def _echo(tokens_in: int) -> dict[str, str]:
    """Пейлоад под заданную цену вызова: FakeEcho берёт tokens_in = len(str(payload))."""
    payload: dict[str, str] = {"data": ""}
    payload["data"] = "x" * (tokens_in - len(str(payload)))
    assert len(str(payload)) == tokens_in
    return payload


def claimed(reversibility: str | None = None, approval: str | None = None, **kw: Any) -> Step:
    """Шаг с заявкой до факта: Step заморожен — заявка задаётся при строительстве."""
    base = step(organ=kw.get("organ", "stateful"), tool=kw.get("tool", "t"), payload=kw.get("payload"), intent=kw.get("intent", "заявка до факта"))
    return dataclasses.replace(base, reversibility=reversibility, approval=approval)


# --- словарь классов (SPEC-0003 п.16) ----------------------------------------


def test_reversibility_classes_dictionary() -> None:
    """Словарь один — blood.envelope.REVERSIBILITY_CLASSES, копий нет (перевод, не дубль)."""
    assert REVERSIBILITY_CLASSES == (
        "reversible",
        "compensatable",
        "partially_reversible",
        "irreversible",
        "unknown",
    )


# --- W-0029: бюджет проверяется и после шага (SPEC-0001 G3) ------------------


def test_last_step_overrun_halts_not_passes(sloop) -> None:
    """F-07: перерасход ПОСЛЕДНИМ шагом — не проход: run() = False, трейс закрыт halt."""
    loop, journal, _ = sloop
    plan = [step(payload=_echo(30)) for _ in range(2)]  # 30 токенов за вызов
    budget = Budget(tokens_in=50)
    assert loop.run(plan, trace_id="w29-last", budget=budget) is False
    events = journal.by_trace("w29-last")
    assert events[-1]["type"] == "halt", "трейс обязан закончиться halt, а не проходом"
    assert "бюджет исчерпан" in events[-1]["payload"]["reason"]
    assert events[-1]["payload"]["at_step"] == 1  # исчерпал последний шаг
    assert journal.totals("w29-last").tokens_in == 60  # перерасход состоялся и оплачен
    # оба шага исполнены и отрефлексированы — halt ПОСЛЕ работы, не вместо
    assert events.count("reflect") == 2 or len([e for e in events if e["type"] == "reflect"]) == 2


def test_budget_within_limits_still_passes(sloop) -> None:
    """Регресс: в лимитах — прежний зелёный проход, лишних halt нет."""
    loop, journal, _ = sloop
    plan = [step(payload=_echo(30)) for _ in range(2)]
    assert loop.run(plan, trace_id="w29-ok", budget=Budget(tokens_in=100)) is True
    assert journal.by_type("halt") == ()
    assert [e["type"] for e in journal.by_trace("w29-ok")] == ["plan", "act", "observe", "reflect"] * 2


# --- W-0024: класс обратимости в плане и акте (SPEC-0003 п.16) ---------------


def test_plan_and_act_carry_declared_class(sloop) -> None:
    """Заявка до факта: план несёт класс, шлюз переносит его в акт."""
    loop, journal, _ = sloop
    s = claimed("compensatable", payload={"key": "k", "value": "v"})
    assert loop.run([s], trace_id="w24-class") is True
    (plan,) = [e for e in journal.by_trace("w24-class") if e["type"] == "plan"]
    (act,) = [e for e in journal.by_trace("w24-class") if e["type"] == "act"]
    assert plan["payload"]["reversibility"] == "compensatable"
    assert act["payload"]["reversibility"] == "compensatable"


def test_undeclared_class_writes_no_field(sloop) -> None:
    """Аддитивность: класс не заявлен — поля нет в крови (старые планы валидны)."""
    loop, journal, _ = sloop
    assert loop.run([step(organ="stateful", tool="t", payload={"key": "k", "value": "v"})], trace_id="w24-none") is True
    (act,) = [e for e in journal.by_trace("w24-none") if e["type"] == "act"]
    assert "reversibility" not in act["payload"]
    assert "reversibility" not in [e for e in journal.by_trace("w24-none") if e["type"] == "plan"][0]["payload"]


def test_unknown_class_is_fail_closed(sloop) -> None:
    """Опечатка не значит молча «unknown»: класс не из словаря — halt до факта."""
    loop, journal, _ = sloop
    s = claimed("revrsible", payload={"key": "k", "value": "v"})  # опечатка
    assert loop.run([s], trace_id="w24-typo") is False
    events = journal.by_trace("w24-typo")
    assert events[-1]["type"] == "halt"
    assert "не понимается" in events[-1]["payload"]["reason"]
    assert not [e for e in events if e["type"] == "act"], "эффекта не было — отказ до факта"


def test_irreversible_without_approval_vetoed_before_fact(sloop) -> None:
    """FR-06: необратимое без одобрения — veto до факта + halt; орган не вызван."""
    loop, journal, gateway = sloop
    s = claimed("irreversible", payload={"key": "k", "value": "v"})
    assert loop.run([s], trace_id="w24-irrev") is False
    events = journal.by_trace("w24-irrev")
    vetoes = [e for e in events if e["type"] == "veto"]
    assert vetoes, "отказ до факта назван veto"
    assert "одобр" in vetoes[0]["payload"]["reason"]
    assert events[-1]["type"] == "halt"  # G1: отказной выход завершён
    assert not [e for e in events if e["type"] == "act"], "акта нет — спрашивали, а не делали"
    assert not gateway._adapters["stateful"].calls, "орган не получил вызова"


def test_irreversible_with_approval_proceeds(sloop) -> None:
    """Одобрение заявлено — необратимое исполняется; заявка видна в плане."""
    loop, journal, _ = sloop
    s = claimed("irreversible", approval="PID 1, 2026-11-03", payload={"key": "k", "value": "v"})
    assert loop.run([s], trace_id="w24-approved") is True
    (plan,) = [e for e in journal.by_trace("w24-approved") if e["type"] == "plan"]
    assert plan["payload"]["approval"] == "PID 1, 2026-11-03"
    assert [e for e in journal.by_trace("w24-approved") if e["type"] == "act"]


def test_gateway_refuses_bad_class_direct(sloop) -> None:
    """Прямой вызов шлюза с чужим классом — veto + SynapseVeto до invoke (fail-closed)."""
    _, journal, gateway = sloop
    with pytest.raises(SynapseVeto):
        gateway.call("stateful", "t", {"key": "k", "value": "v"}, "w24-direct", reversibility="чужой-класс")
    (veto,) = [e for e in journal.by_trace("w24-direct") if e["type"] == "veto"]
    assert "не понимается" in veto["payload"]["reason"]
    assert not [e for e in journal.by_trace("w24-direct") if e["type"] == "act"]


# --- W-0024: компенсация — новая операция (SPEC-0001 п.6, Saga) --------------


def test_compensation_full(sloop) -> None:
    """Полная компенсация: отдельный трейс, causation_id, ключ A01, COMPENSATED."""
    loop, journal, gateway = sloop
    s = claimed("compensatable", payload={"key": "k", "value": "v"})
    assert loop.run([s], trace_id="w24-comp-1") is True
    (act,) = [e for e in journal.by_trace("w24-comp-1") if e["type"] == "act"]
    organ = gateway._adapters["stateful"]
    assert organ.state == {"k": "v"}

    outcome = compensate(journal, gateway, act["id"], accept=FULL, trace_id="w24-comp-1-undo")
    assert outcome["verdict"] == COMPENSATED
    assert outcome["satisfied"] is True
    assert organ.state == {}, "состояние после проверено: ключ откатан"

    trace = journal.by_trace("w24-comp-1-undo")
    types = [e["type"] for e in trace]
    assert "plan" in types and "act" in types and "reflect" in types
    (undo_act,) = [e for e in trace if e["type"] == "act"]
    assert undo_act["payload"]["tool"] == "t_undo"
    assert undo_act["idempotency_key"] == f"compensate:{act['id']}"
    (comp_plan,) = [e for e in trace if e["type"] == "plan"]
    assert comp_plan["causation_id"] == act["id"], "компенсация вызвана актом (честное происхождение)"
    (reflect,) = [e for e in trace if e["type"] == "reflect"]
    assert reflect["payload"]["verdict"] == COMPENSATED
    assert reflect["payload"]["satisfied"] is True


def test_compensation_partial_is_not_pass(sloop) -> None:
    """Частичная компенсация — не PASS: verdict COMPENSATION_PARTIAL, satisfied=false, halt."""
    loop, journal, gateway = sloop
    s = claimed("partially_reversible", payload={"key": "k", "value": "v", "compensation_mode": "partial"})
    assert loop.run([s], trace_id="w24-comp-2") is True
    (act,) = [e for e in journal.by_trace("w24-comp-2") if e["type"] == "act"]

    outcome = compensate(journal, gateway, act["id"], accept=FULL, trace_id="w24-comp-2-undo")
    assert outcome["verdict"] == COMPENSATION_PARTIAL
    assert outcome["satisfied"] is False, "частичная компенсация не проходит как успех"
    trace = journal.by_trace("w24-comp-2-undo")
    assert trace[-1]["type"] == "halt", "незавершённая компенсация закрывает трейс halt (G1)"
    (reflect,) = [e for e in trace if e["type"] == "reflect"]
    assert reflect["payload"]["verdict"] == COMPENSATION_PARTIAL
    assert reflect["payload"]["satisfied"] is False


def test_compensation_of_irreversible_is_refused(sloop) -> None:
    """Необратимое честно не отменяется: NOT_REVERSIBLE, попытки не было (A17)."""
    loop, journal, gateway = sloop
    s = claimed("irreversible", approval="PID 1, 2026-11-03", payload={"key": "k", "value": "v"})
    assert loop.run([s], trace_id="w24-comp-3") is True
    (act,) = [e for e in journal.by_trace("w24-comp-3") if e["type"] == "act"]
    organ = gateway._adapters["stateful"]
    undo_calls_before = len([c for c in organ.calls if c[0] == "t_undo"])

    outcome = compensate(journal, gateway, act["id"], accept=FULL, trace_id="w24-comp-3-undo")
    assert outcome["verdict"] == NOT_REVERSIBLE
    assert outcome["satisfied"] is False
    assert len([c for c in organ.calls if c[0] == "t_undo"]) == undo_calls_before, "инструмент отмены не вызывался"
    trace = journal.by_trace("w24-comp-3-undo")
    assert not [e for e in trace if e["type"] == "act"], "отказ честный: акта компенсации нет"
    assert trace[-1]["type"] == "halt"


def test_compensation_without_declared_compensator_refused(sloop) -> None:
    """У органа нет компенсатора — NOT_REVERSIBLE: дом не выдумывает отмену."""
    loop, journal, gateway = sloop
    assert loop.run([step()], trace_id="w24-comp-4") is True  # sense-a: компенсаторов нет
    (act,) = [e for e in journal.by_trace("w24-comp-4") if e["type"] == "act"]
    outcome = compensate(journal, gateway, act["id"], accept=FULL, trace_id="w24-comp-4-undo")
    assert outcome["verdict"] == NOT_REVERSIBLE
    assert outcome["satisfied"] is False


def test_compensation_requires_acceptance_criterion(sloop) -> None:
    """Без критерия приёмки компенсация не запускается: «результат есть» ≠ «отменено»."""
    loop, journal, gateway = sloop
    s = claimed("compensatable", payload={"key": "k", "value": "v"})
    assert loop.run([s], trace_id="w24-comp-5") is True
    (act,) = [e for e in journal.by_trace("w24-comp-5") if e["type"] == "act"]
    before = len(journal.all())
    with pytest.raises(ValueError):
        compensate(journal, gateway, act["id"], accept=None, trace_id="w24-comp-5-undo")
    assert len(journal.all()) == before, "отказ до факта: кровь не тронута"


def test_compensation_of_missing_act_is_honest_error(sloop) -> None:
    """Акта нет в крови — честная ошибка вызова, кровь не тронута."""
    _, journal, gateway = sloop
    before = len(journal.all())
    with pytest.raises(ValueError):
        compensate(journal, gateway, "00000000-0000-0000-0000-000000000000", accept=FULL)
    assert len(journal.all()) == before


def test_repeat_compensation_does_not_repeat_act(sloop) -> None:
    """A01 + Saga: повторная компенсация не создаёт вторую строку акта."""
    loop, journal, gateway = sloop
    s = claimed("compensatable", payload={"key": "k", "value": "v"})
    assert loop.run([s], trace_id="w24-comp-6") is True
    (act,) = [e for e in journal.by_trace("w24-comp-6") if e["type"] == "act"]

    first = compensate(journal, gateway, act["id"], accept=FULL, trace_id="w24-comp-6-undo-1")
    second = compensate(journal, gateway, act["id"], accept=FULL, trace_id="w24-comp-6-undo-2")
    assert first["verdict"] == COMPENSATED
    assert second["verdict"] == COMPENSATED  # идемпотентный орган: отменять нечего — состояние уже чисто

    undo_acts = [
        e
        for e in journal.all()
        if e["type"] == "act" and e.get("idempotency_key") == f"compensate:{act['id']}"
    ]
    assert len(undo_acts) == 1, "повторная доставка не повторяет эффект: строка акта одна (A01)"
    assert gateway._adapters["stateful"].state == {}


# --- W-0024: дневник говорит по классу (SPEC-0003 п.12/п.16) -----------------


def test_diary_speaks_by_class(sloop) -> None:
    """Дневник: необратимое не отменяется, незаявленное названо, чужой класс назван."""
    from blood.diary import entries

    loop, journal, _ = sloop
    s1 = claimed("irreversible", approval="PID 1", payload={"key": "a", "value": "1"})
    s2 = step(organ="stateful", tool="t", payload={"key": "b", "value": "2"}, intent="без заявки")
    s3 = claimed("compensatable", payload={"key": "c", "value": "3"})
    assert loop.run([s1, s2, s3], trace_id="w24-diary") is True

    book = entries(journal, "w24-diary")
    acts = [r for r in book["records"] if "выполнено" in r["результат"]]
    undo_words = [r["можно ли отменить"] for r in acts]
    assert any("не отменяется" in w for w in undo_words), "необратимое честно названо"
    assert any("не заявлен" in w for w in undo_words), "незаявленный класс назван честно (A02)"
    assert any("компенсаци" in w for w in undo_words), "заявленный класс переведён на человеческий"
