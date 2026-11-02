"""Реконструкция сессии из крови — SPEC-0003 п.8 (v0.5.0): resume.

Кровь — истина: reconstruct восстанавливает только то, что в ней записано
(план, вызовы, наблюдения, вердикты, остановки, полную цену трейса), и ничего
не достраивает. `complete` — трейс закрыт по-записанному: последний конверт —
`halt` либо удовлетворённая `reflect`, и гэпов цепочки в трейсе нет. Гэп не
стирает ткань трейса — он честно доходит до отчёта и роняет `complete`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from blood.envelope import Cost


def _read_envelopes(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Валидные конверты файла в порядке записи + честный счётчик битых строк."""
    envelopes: list[dict[str, Any]] = []
    skipped = 0
    with path.open("rb") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                skipped += 1
                continue
            try:
                envelope = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                skipped += 1
                continue
            if isinstance(envelope, dict) and envelope.get("id"):
                envelopes.append(envelope)
            else:
                skipped += 1
    return envelopes, skipped


def reconstruct(path: str | Path, trace_id: str) -> dict[str, Any]:
    """Восстанавливает сессию ствола мозга по журналу (SPEC-0003 п.8).

    Возвращает отчёт:
    {"trace_id", "events", "plan", "acts", "observes", "reflects", "halts",
     "totals", "complete", "gaps", "skipped"}.

    - plan:     [{"index", "tool", "intent"}] — намерения из событий `plan`;
    - acts:     [{"organ", "tool", "cost", "ts"}] — вызовы с честной ценой;
    - observes: [{"organ", "tool", "result"}];
    - reflects: [{"intent", "satisfied", "reason"}];
    - halts:    [{"reason", "at_step"}];
    - totals:   полная цена трейса (сумма cost всех его конвертов);
    - complete: трейс закрыт по-записанному (halt либо удовлетворённая
      reflect) и гэпов цепочки в его конвертах нет;
    - gaps:     гэпы цепочки prev_id внутри трейса (п.7 — через verify).
    """
    from blood.journal import verify  # локальный импорт: verify — часть журнала, п.7

    path = Path(path)
    report = verify(path)
    envelopes, skipped = _read_envelopes(path)
    trace_events = [e for e in envelopes if e.get("trace_id") == trace_id]
    trace_ids = {e["id"] for e in trace_events}

    plan = [
        {
            "index": e["payload"].get("index"),
            "tool": e["payload"].get("tool"),
            "intent": e["payload"].get("intent"),
        }
        for e in trace_events
        if e["type"] == "plan"
    ]
    acts = [
        {
            "organ": e["organ"],
            "tool": e["payload"].get("tool"),
            "cost": dict(e["cost"]),
            "ts": e["ts"],
        }
        for e in trace_events
        if e["type"] == "act"
    ]
    observes = [
        {
            "organ": e["organ"],
            "tool": e["payload"].get("tool"),
            "result": e["payload"].get("result"),
        }
        for e in trace_events
        if e["type"] == "observe"
    ]
    reflects = [
        {
            "intent": e["payload"].get("intent"),
            "satisfied": e["payload"].get("satisfied", False),
            "reason": e["payload"].get("reason"),
        }
        for e in trace_events
        if e["type"] == "reflect"
    ]
    halts = [
        {
            "reason": e["payload"].get("reason"),
            "at_step": e["payload"].get("at_step"),
        }
        for e in trace_events
        if e["type"] == "halt"
    ]

    total = Cost()
    for envelope in trace_events:
        total += Cost.from_dict(envelope["cost"])

    gaps = [gap for gap in report["gaps"] if gap["id"] in trace_ids]
    last = trace_events[-1] if trace_events else None
    complete = bool(trace_events) and not gaps and (
        last["type"] == "halt"
        or (last["type"] == "reflect" and last["payload"].get("satisfied") is True)
    )

    return {
        "trace_id": trace_id,
        "events": len(trace_events),
        "plan": plan,
        "acts": acts,
        "observes": observes,
        "reflects": reflects,
        "halts": halts,
        "totals": total.as_dict(),
        "complete": complete,
        "gaps": gaps,
        "skipped": skipped,
    }
