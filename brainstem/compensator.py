# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Компенсация — обратимость честным языком (W-0024, SPEC-0001 п.6).

Saga-зерно пакета «Human Membrane» (FR-05/FR-06, ADR-002): отмена — новая
операция-компенсация, не редактирование прошлого. Кровь append-only (п.4
SPEC-0003) — отмена ничего не вычёркивает: она добавляет новый факт.

Правила дома (спека раньше кода — SPEC-0001 v0.4.0 п.6):

- компенсация — отдельный трейс с ``causation_id`` = id отменяемого акта
  (честное происхождение, SPEC-0003 п.10: компенсация вызвана актом);
- идемпотентный ключ ``compensate:{act_id}`` (A01, SPEC-0003 п.9): повторная
  компенсация не создаёт вторую строку акта — кровь возвращает записанный;
- проверка состояния после обязательна: без критерия приёмки (грамматика
  W-0027) компенсация не запускается — «результат есть» ≠ «отменено»;
- вердикты словаря пакета: COMPENSATED / COMPENSATION_PARTIAL / NOT_REVERSIBLE;
  частичная компенсация — не PASS (satisfied=False), трейс закрыт halt (G1);
  частичность заявляет сам орган в результате (``"compensation": "partial"``) —
  дом не догадывается;
- необратимое честно не отменяется: класс акта irreversible или компенсатор
  не объявлен манифестом — NOT_REVERSIBLE, попытки не было (A17);
- критерий меряет отчёт органа о состоянии после — дом читает отчёт,
  не лезет в чужой орган за синапсами.
"""
from __future__ import annotations

from typing import Any, Callable

from blood.envelope import Cost, make, new_trace_id
from blood.journal import Journal
from brainstem.loop import _normalize, measure_criterion
from synapse.gateway import (
    AuthorityViolation,
    BloodRecordError,
    OrganUnavailable,
    SynapseVeto,
)

# Вердикты — словарь пакета «Human Membrane» (ADR-002), перевод, не копия.
COMPENSATED = "COMPENSATED"
COMPENSATION_PARTIAL = "COMPENSATION_PARTIAL"
NOT_REVERSIBLE = "NOT_REVERSIBLE"

Accept = dict[str, Any] | Callable[[Any], bool]

_GATEWAY_FAILURES = (SynapseVeto, OrganUnavailable, AuthorityViolation, BloodRecordError)


def _find_act(journal: Journal, act_id: str) -> dict[str, Any] | None:
    """Кровь — истина: акт ищется в живом журнале (сессия или присоединённый файл)."""
    for envelope in journal.all():
        if envelope.get("id") == act_id:
            return envelope
    return None


def compensate(
    journal: Journal,
    gateway: Any,
    act_id: str,
    accept: Accept | None,
    *,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Отменяет эффект акта новой операцией-компенсацией (W-0024, SPEC-0001 п.6).

    Возвращает итог операции: {"verdict", "satisfied", "trace_id", "act_id",
    "reason"}. Вердикты — словарь пакета: COMPENSATED / COMPENSATION_PARTIAL /
    NOT_REVERSIBLE; reason назван, когда удовлетворения нет.

    Отказы до факта — ValueError без записи в кровь: операция не начата,
    кровь не тронута (акт не найден; критерий приёмки не задан — «результат
    есть» ≠ «отменено», W-0027). Отказ после начала — честно в крови:
    NOT_REVERSIBLE (необратимое или компенсатор не объявлен — попытки не было,
    A17), отказ шлюза — reflect + halt (G1: трейс полон).
    """
    if accept is None:
        raise ValueError(
            "компенсация без критерия приёмки не запускается: "
            "«результат есть» ≠ «отменено» (W-0027, SPEC-0001 п.6)"
        )

    act = _find_act(journal, act_id)
    if act is None or act.get("type") != "act":
        raise ValueError(f"акта {act_id} нет в крови — отменять нечего (кровь — истина)")

    trace = trace_id or new_trace_id()
    act_payload = act.get("payload") or {}
    tool = act_payload.get("tool")
    organ = act["organ"]

    def _plan() -> None:
        journal.append(
            make(
                "plan",
                "brainstem",
                organ,
                trace,
                {
                    "what": f"компенсация акта {act_id[:8]}",
                    "intent": f"отменить эффект акта {act_id[:8]}",
                    "tool": tool,
                    "act_id": act_id,
                },
                Cost(),
                causation_id=act_id,
            )
        )

    def _reflect(payload: dict[str, Any]) -> None:
        journal.append(make("reflect", "brainstem", organ, trace, payload, Cost(), causation_id=act_id))

    def _halt(reason: str) -> None:
        journal.append(make("halt", "brainstem", organ, trace, {"reason": reason}, Cost(), causation_id=act_id))

    # Необратимое честно не отменяется — попытки не было (A17): класс акта
    # — заявление автора действия, компенсатор к необратимому не применяется.
    if act_payload.get("reversibility") == "irreversible":
        _plan()
        _reflect({"verdict": NOT_REVERSIBLE, "satisfied": False, "reason": "класс акта — irreversible: не отменяется"})
        _halt("отказ: необратимое действие не отменяется (W-0024)")
        return {
            "verdict": NOT_REVERSIBLE,
            "satisfied": False,
            "trace_id": trace,
            "act_id": act_id,
            "reason": "класс акта — irreversible: не отменяется",
        }

    undo_tool = gateway.compensator_for(organ, tool)
    if undo_tool is None:
        _plan()
        _reflect(
            {
                "verdict": NOT_REVERSIBLE,
                "satisfied": False,
                "reason": f"компенсатор не объявлен манифестом: {organ}.{tool}",
            }
        )
        _halt(f"отказ: у {organ}.{tool} нет компенсатора — отмена не выдумывается")
        return {
            "verdict": NOT_REVERSIBLE,
            "satisfied": False,
            "trace_id": trace,
            "act_id": act_id,
            "reason": f"компенсатор не объявлен манифестом: {organ}.{tool}",
        }

    _plan()
    try:
        result = gateway.call(
            organ,
            undo_tool,
            act_payload.get("payload") or {},
            trace,
            idempotency_key=f"compensate:{act_id}",
        )
    except _GATEWAY_FAILURES as failure:
        _reflect({"verdict": None, "satisfied": False, "reason": f"шлюз: {failure}"})
        _halt(f"компенсация не дошла до органа: {failure}")
        return {"verdict": None, "satisfied": False, "trace_id": trace, "act_id": act_id, "reason": f"шлюз: {failure}"}

    journal.append(
        make("observe", "brainstem", organ, trace, {"result": _normalize(result), "tool": undo_tool}, Cost(), causation_id=act_id)
    )

    criterion, ok, why = measure_criterion(accept, result)
    if ok:
        _reflect({"verdict": COMPENSATED, "criterion": criterion, "satisfied": True})
        return {"verdict": COMPENSATED, "satisfied": True, "trace_id": trace, "act_id": act_id, "reason": None}

    # Частичность заявляет сам орган в результате — дом не догадывается.
    if isinstance(result, dict) and result.get("compensation") == "partial":
        reason = why or "компенсация частична"
        _reflect({"verdict": COMPENSATION_PARTIAL, "criterion": criterion, "satisfied": False, "reason": reason})
        _halt(f"компенсация частична: состояние после не принято критерием")
        return {
            "verdict": COMPENSATION_PARTIAL,
            "satisfied": False,
            "trace_id": trace,
            "act_id": act_id,
            "reason": reason,
        }

    reason = why or "компенсация не принята критерием"
    _reflect({"verdict": None, "criterion": criterion, "satisfied": False, "reason": reason})
    _halt(f"компенсация не принята: {reason}")
    return {"verdict": None, "satisfied": False, "trace_id": trace, "act_id": act_id, "reason": reason}
