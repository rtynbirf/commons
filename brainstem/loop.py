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
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import jsonschema

from blood.envelope import REVERSIBILITY_CLASSES, Cost, make, new_trace_id
from blood.journal import Journal
from brainstem.attention import attention_cost
from brainstem.silence import ANSWER_APPROVED, ApprovalRequest, await_approval
from memory import Memory
from synapse.gateway import AuthorityViolation, BloodRecordError, Gateway, OrganUnavailable, SynapseVeto


@dataclass(frozen=True)
class Step:
    """Один шаг плана: намерение + вызов органа через синапсы.

    `accept` (W-0027, SPEC-0001 v0.3.0) — проверяемый критерий приёмки
    результата: JSON-схема (dict) или предикат (callable result→bool).
    None — прежняя рефлексия M1 (результат есть — удовлетворено).

    `reversibility` (W-0024, SPEC-0001 v0.4.0 п.5, SPEC-0003 п.16) — заявка
    класса обратимости ДО факта: reversible / compensatable /
    partially_reversible / irreversible / unknown (словарь —
    `blood.envelope.REVERSIBILITY_CLASSES`). None — не заявлено: старые планы
    валидны (аддитивно), кровь поля не получает, дневник честно называет
    незаявленное. Класс не из словаря — дефект плана: halt до факта.

    `approval` (W-0024, FR-06) — кто одобрил необратимое ДО факта: строка-заявка
    («PID 1, 2026-11-03»), доверие unverified по природе. Необратимое без
    одобрения ствол не исполняет — veto до факта (спрашивать = остановиться
    и назвать, чего не хватает; решение — за Человеком, не за циклом).

    `approval_window` (W-0032, SPEC-0004 п.8, SPEC-0001 v0.5.0 п.7) — окно
    тишины в секундах: живой контур одобрения перед ACT — кровь несёт
    approval.requested → granted/veto (воля Человека, source pid1) /
    expired (окно истекло — отмена по-записанному, тишина = «нет»);
    до органа шаг не доходит без ответа. Когда окно объявлено, вето
    «необратимое без одобрения» откладывается до вердикта контура —
    спрашивать по-настоящему лучше, чем остановиться от отсутствия нерва.
    Вопрос о необратимом шаге — P0-прерывание (W-0025): запрос несёт
    `cost.attention=1` — остановка и вопрос Человеку — заявленная цена.
    `approval_why` — зачем одобрение, попадает в approval.requested;
    пусто — берётся намерение шага.
    """

    organ: str
    tool: str
    payload: dict[str, Any] = field(default_factory=dict)
    intent: str = ""
    accept: dict[str, Any] | Callable[[Any], bool] | None = None
    reversibility: str | None = None
    approval: str | None = None
    approval_window: float | None = None
    approval_why: str = ""


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

    Инвариант halt (SPEC-0001 G1): любой отказной выход цикла завершён
    событием halt — G1-реконструкция трейса всегда полна.

    Рефлексия (SPEC-0001 v0.3.0, W-0027): шаг может объявить проверяемый
    критерий успеха (`Step.accept`) — JSON-схему или предикат; тогда REFLECT
    меряет результат им, а не фактом непустого ответа («error с ok:false»
    успехом не считается, F-06). Без критерия — прежняя рефлексия M1
    (результат есть — удовлетворено), аддитивно: старые планы валидны.
    Кровь честная: reflect называет критерий (`criterion`) — чем мерили.
    """

    def __init__(
        self,
        gateway: Gateway,
        journal: Journal,
        *,
        memory: Memory | None = None,
        organ_budgets: dict[str, Budget] | None = None,
        approval_channel: Callable[[dict[str, Any]], str | None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.gateway = gateway
        self.journal = journal
        self.memory = memory
        # Per-call лимиты органов (M3 SPEC-0001 G3): данные из манифеста
        # (brainstem.budget.budgets_from_manifest), ствол мозга знает их как параметры.
        self.organ_budgets = organ_budgets or {}
        # Контур одобрения (W-0032): канал Человека + инъекция времени для приёмок.
        self.approval_channel = approval_channel
        self.clock = clock
        self.sleeper = sleeper

    # --- кровь ---

    def _emit(
        self,
        event_type: str,
        organ: str,
        payload: dict[str, Any],
        trace_id: str,
        cost: Cost | None = None,
    ) -> dict[str, Any]:
        """Пишет конверт в кровь и возвращает его — память помнит уже записанное (SPEC-0005 п.1).

        Цена задаётся эмитентом: прерывание Человека (вопрос об одобрении,
        W-0025) заявляет расход внимания в `cost.attention`; незаявленное
        — нулей не получает (A02, SPEC-0003 п.17).
        """
        return self.journal.append(make(event_type, "brainstem", organ, trace_id, payload, cost or Cost()))

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

    # --- рефлексия по проверяемому критерию (W-0027, SPEC-0001 v0.3.0) ---

    @staticmethod
    def _accept(step: "Step", result: Any) -> tuple[str, bool, str | None]:
        """Меряет результат критерием шага (см. measure_criterion)."""
        return measure_criterion(step.accept, result)

    # --- цикл ---

    def run(self, plan: list[Step], trace_id: str | None = None, budget: Budget | None = None) -> bool:
        """Выполняет план.

        True — все намерения удовлетворены; False — HALT (событие halt в крови,
        причина в payload.reason).

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
            if step.reversibility is not None:
                plan_payload["reversibility"] = step.reversibility  # заявка ДО факта (W-0024, п.5)
            if step.approval is not None:
                plan_payload["approval"] = step.approval  # кто одобрил (заявка, unverified по природе)
            memory_context = self._recall(step.intent, trace_id)  # read-only, до PLAN (SPEC-0005 п.5)
            if memory_context:
                plan_payload["memory_context"] = memory_context
            self._emit("plan", step.organ, plan_payload, trace_id)
            # Обратимость до факта (W-0024, SPEC-0001 v0.4.0 п.5): чужой класс — дефект
            # плана, опечатка не значит молча «unknown» (ADR-0014); необратимое без
            # одобрения — veto до факта: спрашивать = остановиться и назвать.
            if step.reversibility is not None and step.reversibility not in REVERSIBILITY_CLASSES:
                self._emit(
                    "halt",
                    "self",
                    {"reason": f"класс обратимости не понимается: {step.reversibility!r}", "at_step": index},
                    trace_id,
                )
                return False
            if step.reversibility == "irreversible" and not step.approval and step.approval_window is None:
                # (W-0032, SPEC-0004 п.8): окно тишины — это и есть спрашивание живьём; без окна —
                # остановиться до факта и назвать, чего не хватает.
                self._emit(
                    "veto",
                    "self",
                    {
                        "reason": "необратимое действие требует одобрения до факта (W-0024, FR-06)",
                        "tool": step.tool,
                        "reversibility": "irreversible",
                        "at_step": index,
                    },
                    trace_id,
                    cost=Cost(attention=attention_cost("P0")),  # остановка и вопрос Человеку — заявленная цена (W-0025)
                )
                self._emit("halt", "self", {"reason": "необратимое действие не одобрено — остановка до факта", "at_step": index}, trace_id)
                return False
            # Проверка ДО факта (F-03, волна №20): несериализуемый payload шага не доходит
            # до органа — эффект не случается без крови (закон 2), трейс завершён halt (G1).
            try:
                json.dumps(step.payload, ensure_ascii=False)
            except (TypeError, ValueError) as exc:
                self._emit("halt", "self", {"reason": f"payload шага не сериализуется в кровь: {exc}", "at_step": index}, trace_id)
                return False
            if step.approval_window is not None:
                # Одобрение перед необратимым живьём (W-0032, SPEC-0004 п.8, SPEC-0001 v0.5.0 п.7):
                # тишина = «нет» по-записанному, до органа шаг не доходит без ответа.
                if self.approval_channel is None:
                    self._emit("error", "self", {"reason": "канал одобрения не подключён, а шаг требует окна", "what": f"{step.organ}.{step.tool}"}, trace_id)
                    self._remember(self._emit("reflect", "self", {"intent": step.intent, "satisfied": False, "reason": "approval: канал не подключён"}, trace_id))
                    self._emit("halt", "self", {"reason": f"канал одобрения не подключён: шаг {index} требует окна", "at_step": index}, trace_id)
                    return False
                verdict = await_approval(
                    self.journal,
                    trace_id,
                    ApprovalRequest(
                        what=f"{step.organ}.{step.tool}",
                        window_s=step.approval_window,
                        why=step.approval_why or step.intent,
                        # Вопрос о необратимом — P0-прерывание: цена внимания названа (W-0025)
                        priority="P0" if step.reversibility == "irreversible" else None,
                    ),
                    self.approval_channel,
                    clock=self.clock,
                    sleeper=self.sleeper,
                )
                if verdict != ANSWER_APPROVED:
                    self._remember(self._emit("reflect", "self", {"intent": step.intent, "satisfied": False, "reason": f"approval: {verdict}"}, trace_id))
                    self._emit("halt", "self", {"reason": f"одобрение не получено ({verdict}): тишина = «нет»" if verdict == "expired" else f"одобрение не получено ({verdict})", "at_step": index}, trace_id)
                    return False
            try:
                result = self.gateway.call(
                    step.organ, step.tool, step.payload, trace_id, reversibility=step.reversibility
                )
            except SynapseVeto as veto:
                self._remember(self._emit("reflect", "self", {"intent": step.intent, "satisfied": False, "reason": f"veto: {veto}"}, trace_id))
                self._emit("halt", "self", {"reason": f"veto: {veto}", "at_step": index}, trace_id)
                return False
            except OrganUnavailable as failure:
                self._remember(self._emit("reflect", "self", {"intent": step.intent, "satisfied": False, "reason": f"organ: {failure}"}, trace_id))
                self._emit("halt", "self", {"reason": f"орган недоступен: {failure}", "at_step": index}, trace_id)
                return False
            except AuthorityViolation as violation:
                # SPEC-0002 п.8: нарушителя не заменяют молча — reflect + halt, трейс полон.
                self._remember(self._emit("reflect", "self", {"intent": step.intent, "satisfied": False, "reason": f"security: {violation}"}, trace_id))
                self._emit("halt", "self", {"reason": f"полномочия превышены: {violation}", "at_step": index}, trace_id)
                return False
            except BloodRecordError as broken:
                # Эффект без крови (F-03, волна №20): орган отработал, кровь не приняла акт —
                # трейс завершён halt (G1), причина и в reflect, и в halt; эффект случился —
                # назван в крови error-конвертом шлюза, не спрятан.
                self._remember(self._emit("reflect", "self", {"intent": step.intent, "satisfied": False, "reason": f"кровь: {broken}"}, trace_id))
                self._emit("halt", "self", {"reason": f"эффект без крови: {broken}", "at_step": index}, trace_id)
                return False

            # Per-call лимит (M3 SPEC-0001 G3): вызов оплачен — превышение фиксируем алертом.
            organ_budget = self.organ_budgets.get(step.organ)
            if organ_budget is not None:
                over = organ_budget.per_call_exceeded_by(self._delta(self.journal.totals(trace_id), spent))
                if over is not None:
                    self._emit("alert", step.organ, {"reason": f"лимит вызова превышен: {over}", "tool": step.tool}, trace_id)

            self._emit("observe", step.organ, {"result": _normalize(result), "tool": step.tool}, trace_id)
            criterion, satisfied, why = self._accept(step, result)
            reflect_payload: dict[str, Any] = {
                "intent": step.intent,
                "satisfied": satisfied,
                "criterion": criterion,
            }
            if why is not None:
                reflect_payload["reason"] = why
            self._remember(self._emit("reflect", "self", reflect_payload, trace_id))
            if not satisfied:
                reason = why or "орган вернул пустой результат"
                self._emit("halt", "self", {"reason": f"намерение не удовлетворено: {reason}", "at_step": index}, trace_id)
                return False

            # W-0029 (SPEC-0001 G3, 0.4.0, зерно коллег F-07): бюджет проверяется и
            # ПОСЛЕ шага — перерасход последним шагом не проходит молча: трейс
            # завершён halt, а не проходом (G1: отказной выход завершён halt).
            exhausted_after = budget.exhausted_by(self.journal.totals(trace_id))
            if exhausted_after is not None:
                self._emit(
                    "halt",
                    "self",
                    {"reason": f"бюджет исчерпан: {exhausted_after}", "at_step": index},
                    trace_id,
                )
                return False
        return True


def measure_criterion(
    accept: dict[str, Any] | Callable[[Any], bool] | None, result: Any
) -> tuple[str, bool, str | None]:
    """Меряет результат критерием приёмки (W-0027, SPEC-0001 v0.3.0/п.4).

    Возвращает (критерий, вердикт, причина). Общая грамматика цикла (Step.accept)
    и компенсатора (проверка состояния после — SPEC-0001 п.6): одна машина,
    чтобы честность не расходилась. JSON-схема — jsonschema; предикат —
    callable, исключение предиката — провал с названной причиной (дефект
    плана, не органа); непонятный критерий — fail-closed: намерение
    не удовлетворено, причина названа.
    """
    if accept is None:
        return "m1", result is not None, None
    if isinstance(accept, dict):
        try:
            jsonschema.validate(result, accept)
        except jsonschema.ValidationError as exc:
            return "jsonschema", False, f"результат не принят по схеме шага: {exc.message}"
        return "jsonschema", True, None
    if callable(accept):
        try:
            return "predicate", bool(accept(result)), None
        except Exception as exc:  # noqa: BLE001 — упавший критерий — дефект плана, не органа
            return "predicate", False, f"критерий шага упал: {exc!r}"
    return "unknown", False, f"критерий шага не понимается: {type(accept).__name__}"


def _normalize(result: Any) -> Any:
    """Наблюдение должно быть сериализуемым — кровь не принимает живые объекты."""
    if isinstance(result, dict):
        return {k: _normalize(v) for k, v in result.items()}
    if isinstance(result, (list, tuple)):
        return [_normalize(v) for v in result]
    if isinstance(result, (str, int, float, bool)) or result is None:
        return result
    return repr(result)
