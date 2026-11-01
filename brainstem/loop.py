"""Канонический цикл агента — SPEC-0001.

Инварианты:
- G1 Трассируемость: каждый переход — событие в крови с trace_id.
- G2 Заменяемость: смена органа не меняет цикл — меняется манифест/адаптер.
- G3 Бюджет: при исчерпании лимита — HALT с событием `halt`.

Цикл не знает ни одного органа и не умеет их вызывать напрямую:
весь доступ — через синапсы (gateway.call). Прямого пути к органу из цикла нет.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from blood.envelope import Cost, make, new_trace_id
from blood.journal import Journal
from synapse.gateway import Gateway, OrganUnavailable, SynapseVeto


@dataclass(frozen=True)
class Step:
    """Один шаг плана: намерение + вызов органа через синапсы."""

    organ: str
    tool: str
    payload: dict[str, Any] = field(default_factory=dict)
    intent: str = ""


@dataclass
class Budget:
    """Бюджет метаболизма (G3). None — лимит не задан."""

    tokens_in: int | None = None
    tokens_out: int | None = None
    seconds: float | None = None

    def exhausted_by(self, spent: Cost) -> str | None:
        """Граница включена: проведённое ровно в лимит = бюджет исчерпан (SPEC-0001 G3)."""
        if self.tokens_in is not None and spent.tokens_in >= self.tokens_in:
            return f"tokens_in {spent.tokens_in} >= {self.tokens_in}"
        if self.tokens_out is not None and spent.tokens_out >= self.tokens_out:
            return f"tokens_out {spent.tokens_out} >= {self.tokens_out}"
        if self.seconds is not None and spent.seconds >= self.seconds:
            return f"seconds {spent.seconds:.3f} >= {self.seconds}"
        return None


class Loop:
    """Ствол мозга: план → действие → наблюдение → рефлексия."""

    def __init__(self, gateway: Gateway, journal: Journal) -> None:
        self.gateway = gateway
        self.journal = journal

    # --- кровь ---

    def _emit(self, event_type: str, organ: str, payload: dict[str, Any], trace_id: str) -> None:
        self.journal.append(make(event_type, "brainstem", organ, trace_id, payload, Cost()))

    # --- приёмка G3: бюджет читается из крови, а не из памяти цикла ---

    def _budget_verdict(self, trace_id: str, budget: Budget) -> str | None:
        return budget.exhausted_by(self.journal.totals(trace_id))

    # --- цикл ---

    def run(self, plan: list[Step], trace_id: str | None = None, budget: Budget | None = None) -> bool:
        """Выполняет план. True — все намерения удовлетворены; False — HALT.

        Пустой план — ошибка: цикл без намерения не запускается (SPEC-0001 PLAN).
        """
        if not plan:
            self._emit("halt", "self", {"reason": "пустой план: нет намерения"}, trace_id or new_trace_id())
            return False

        trace_id = trace_id or new_trace_id()
        budget = budget or Budget()

        for index, step in enumerate(plan):
            reason = self._budget_verdict(trace_id, budget)
            if reason is not None:
                self._emit("halt", "self", {"reason": f"бюджет исчерпан: {reason}", "at_step": index}, trace_id)
                return False

            self._emit("plan", step.organ, {"index": index, "tool": step.tool, "intent": step.intent}, trace_id)
            try:
                result = self.gateway.call(step.organ, step.tool, step.payload, trace_id)
            except SynapseVeto as veto:
                self._emit("reflect", "self", {"intent": step.intent, "satisfied": False, "reason": f"veto: {veto}"}, trace_id)
                return False
            except OrganUnavailable as failure:
                self._emit("reflect", "self", {"intent": step.intent, "satisfied": False, "reason": f"organ: {failure}"}, trace_id)
                return False

            self._emit("observe", step.organ, {"result": _normalize(result), "tool": step.tool}, trace_id)
            satisfied = result is not None  # рефлексия M1: намерение = вызов вернул результат
            self._emit("reflect", "self", {"intent": step.intent, "satisfied": satisfied}, trace_id)
            if not satisfied:
                return False
        return True


def _normalize(result: Any) -> Any:
    """Наблюдение должно быть сериализуемым — кровь не принимает живые объекты."""
    if isinstance(result, dict):
        return {k: _normalize(v) for k, v in result.items()}
    if isinstance(result, (list, tuple)):
        return [_normalize(v) for v in result]
    if isinstance(result, (str, int, float, bool)) or result is None:
        return result
    return repr(result)
