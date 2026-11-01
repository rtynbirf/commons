"""Канонический цикл агента — SPEC-0001.

Инварианты:
- G1 Трассируемость: каждый переход — событие в крови с trace_id.
- G2 Заменяемость: смена органа не меняет цикл — меняется манифест/адаптер.
- G3 Бюджет: при исчерпании лимита — HALT с событием `halt`.

Цикл не знает ни одного органа и не умеет их вызывать напрямую:
весь доступ — через синапсы (gateway.call). Прямого пути к органу из цикла нет.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Any

from blood.envelope import Cost, make, new_trace_id
from blood.journal import Journal
from memory import Memory
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
    """Бюджет метаболизма (G3). None — лимит не задан.

    Три границы (M3 SPEC-0001 G3):
    - exhausted_by — исчерпание трейс-бюджета: HALT (граница включена);
    - alerted_by — порог алерта от лимита: событие `alert` (один раз на трейс);
    - per_call_exceeded_by — лимит ОДНОГО вызова (из манифеста, данные —
      brainstem.budget.budgets_from_manifest): вызов уже оплачен кровью — это
      не запрет, а алерт с именем органа.
    """

    tokens_in: int | None = None
    tokens_out: int | None = None
    seconds: float | None = None
    alert_ratio: float = 0.8

    def exhausted_by(self, spent: Cost) -> str | None:
        """Граница включена: проведённое ровно в лимит = бюджет исчерпан (SPEC-0001 G3)."""
        if self.tokens_in is not None and spent.tokens_in >= self.tokens_in:
            return f"tokens_in {spent.tokens_in} >= {self.tokens_in}"
        if self.tokens_out is not None and spent.tokens_out >= self.tokens_out:
            return f"tokens_out {spent.tokens_out} >= {self.tokens_out}"
        if self.seconds is not None and spent.seconds >= self.seconds:
            return f"seconds {spent.seconds:.3f} >= {self.seconds}"
        return None

    def alerted_by(self, spent: Cost) -> str | None:
        """Порог алерта (alert_ratio от лимита), но без исчерпания — иначе это уже halt."""
        for limit, actual, name in (
            (self.tokens_in, spent.tokens_in, "tokens_in"),
            (self.tokens_out, spent.tokens_out, "tokens_out"),
            (self.seconds, spent.seconds, "seconds"),
        ):
            if limit is None:
                continue
            threshold = limit * self.alert_ratio
            if threshold <= actual < limit:
                form = f"{actual:.3f}" if name == "seconds" else str(actual)
                return f"{name} {form} >= {threshold:g} ({name} лимита {limit})"
        return None

    def per_call_exceeded_by(self, spent: Cost) -> str | None:
        """Лимит одного вызова: строго больше — вызов состоялся и оплачен, фиксируем алертом."""
        if self.tokens_in is not None and spent.tokens_in > self.tokens_in:
            return f"tokens_in {spent.tokens_in} > {self.tokens_in}"
        if self.tokens_out is not None and spent.tokens_out > self.tokens_out:
            return f"tokens_out {spent.tokens_out} > {self.tokens_out}"
        if self.seconds is not None and spent.seconds > self.seconds:
            return f"seconds {spent.seconds:.3f} > {self.seconds}"
        return None


class Loop:
    """Ствол мозга: план → действие → наблюдение → рефлексия.

    Память (SPEC-0005) — необязательный кэш-советник: PLAN читает её read-only
    перед планом, индексация — только после REFLECT. Отказ памяти — degrade:
    событие error в кровь, цикл продолжает без неё; кровь остаётся истиной.
    """

    def __init__(
        self,
        gateway: Gateway,
        journal: Journal,
        *,
        memory: Memory | None = None,
        organ_budgets: dict[str, Budget] | None = None,
    ) -> None:
        self.gateway = gateway
        self.journal = journal
        self.memory = memory
        # Per-call лимиты органов (M3 SPEC-0001 G3): данные из манифеста
        # (brainstem.budget.budgets_from_manifest), ствол мозга знает их как параметры.
        self.organ_budgets = organ_budgets or {}

    # --- кровь ---

    def _emit(self, event_type: str, organ: str, payload: dict[str, Any], trace_id: str) -> dict[str, Any]:
        """Пишет конверт в кровь и возвращает его — память помнит уже записанное (SPEC-0005 п.1)."""
        return self.journal.append(make(event_type, "brainstem", organ, trace_id, payload, Cost()))

    # --- память (SPEC-0005): кэш-советник, отказ — degrade, кровь — истина ---

    def _recall(self, intent: str, trace_id: str) -> list[dict[str, Any]]:
        """Read-only контекст памяти перед PLAN (SPEC-0005 п.5).

        Память недоступна — событие error в кровь, шаг идёт без контекста
        (degrade SPEC-0005): отказ памяти никогда не останавливает цикл.
        Возвращается копия: память не должна иметь шанса мутировать кровь.
        """
        if self.memory is None:
            return []
        try:
            return copy.deepcopy(self.memory.context(intent))
        except Exception:  # noqa: BLE001 — отказной режим SPEC-0005: цикл живёт без памяти
            self._emit("error", "memory", {"reason": "memory_unavailable"}, trace_id)
            return []

    def _remember(self, envelope: dict[str, Any]) -> None:
        """Индексация после REFLECT (SPEC-0005 п.1): рефлексия уже в крови.

        Память упала — событие error в кровь, цикл продолжается без неё
        (degrade SPEC-0005); сам REFLECT-конверт не трогается — кровь истина.
        """
        if self.memory is None:
            return
        try:
            self.memory.observe(envelope)
        except Exception:  # noqa: BLE001 — отказной режим SPEC-0005
            self._emit("error", "memory", {"reason": "memory_unavailable"}, envelope["trace_id"])

    # --- приёмка G3: бюджет читается из крови, а не из памяти цикла ---

    @staticmethod
    def _delta(after: Cost, before: Cost) -> Cost:
        """Цена одного вызова = разница totals крови до/после (кровь — истина)."""
        return Cost(
            tokens_in=after.tokens_in - before.tokens_in,
            tokens_out=after.tokens_out - before.tokens_out,
            seconds=round(after.seconds - before.seconds, 6),
        )

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
        alerted = False  # один alert на трейс: кровь не засоряем спамом

        for index, step in enumerate(plan):
            spent = self.journal.totals(trace_id)
            reason = budget.exhausted_by(spent)
            if reason is not None:
                self._emit("halt", "self", {"reason": f"бюджет исчерпан: {reason}", "at_step": index}, trace_id)
                return False
            if not alerted:
                warning = budget.alerted_by(spent)
                if warning is not None:
                    self._emit("alert", "self", {"reason": f"бюджет близок к исчерпанию: {warning}", "at_step": index}, trace_id)
                    alerted = True

            plan_payload: dict[str, Any] = {"index": index, "tool": step.tool, "intent": step.intent}
            memory_context = self._recall(step.intent, trace_id)  # read-only, до PLAN (SPEC-0005 п.5)
            if memory_context:
                plan_payload["memory_context"] = memory_context
            self._emit("plan", step.organ, plan_payload, trace_id)
            try:
                result = self.gateway.call(step.organ, step.tool, step.payload, trace_id)
            except SynapseVeto as veto:
                self._remember(self._emit("reflect", "self", {"intent": step.intent, "satisfied": False, "reason": f"veto: {veto}"}, trace_id))
                return False
            except OrganUnavailable as failure:
                self._remember(self._emit("reflect", "self", {"intent": step.intent, "satisfied": False, "reason": f"organ: {failure}"}, trace_id))
                return False

            # Per-call лимит (M3 SPEC-0001 G3): вызов оплачен — превышение фиксируем алертом.
            organ_budget = self.organ_budgets.get(step.organ)
            if organ_budget is not None:
                over = organ_budget.per_call_exceeded_by(self._delta(self.journal.totals(trace_id), spent))
                if over is not None:
                    self._emit("alert", step.organ, {"reason": f"лимит вызова превышен: {over}", "tool": step.tool}, trace_id)

            self._emit("observe", step.organ, {"result": _normalize(result), "tool": step.tool}, trace_id)
            satisfied = result is not None  # рефлексия M1: намерение = вызов вернул результат
            self._remember(self._emit("reflect", "self", {"intent": step.intent, "satisfied": satisfied}, trace_id))
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
