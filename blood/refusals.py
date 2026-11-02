"""Счётчик честных отказов — W-0021 (Ф-0.3, волна №16).

Зерно «совести» коллеги-LLM (docs/colleague-synthesis.md, п.9, волна №14):
честный отказ — данные, а не стыд. Счётчик считает провалы живой крови,
а не хвалит за них: `veto` (сказано «нет»), `halt` (остановились),
`error` (ошиблись), `security.violation` (остановлено стражем).
plan/act/observe/reflect/boot/shutdown/organ.* — не отказы, в счёт не входят:
счётчик считает провалы, а не размывает жанр.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Union

from blood.journal import Journal

REFUSAL_TYPES: tuple[str, ...] = ("veto", "halt", "error", "security.violation")


def count_refusals(source: Union[Journal, str, Path]) -> dict[str, Any]:
    """Считает честные отказы живой крови (W-0021).

    Принимает Journal (память сессии) или путь к blood.jsonl (пролитая
    кровь). Возвращает честный отчёт: {"total": N, "by_type": {...},
    "traces": {trace_id: N}, "skipped": S} — битые строки названы, а не
    молча съедены (тот же закон честности, что у Journal.skipped).
    """
    by_type: dict[str, int] = {}
    traces: dict[str, int] = {}
    total = 0
    skipped = 0

    if isinstance(source, Journal):
        events = list(source.all())
    else:
        path = Path(source)
        events = []
        if path.exists():
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
                    if not isinstance(envelope, dict):
                        skipped += 1
                        continue
                    events.append(envelope)

    for envelope in events:
        event_type = envelope.get("type")
        if event_type in REFUSAL_TYPES:
            total += 1
            by_type[event_type] = by_type.get(event_type, 0) + 1
            trace_id = envelope.get("trace_id", "?")
            traces[trace_id] = traces.get(trace_id, 0) + 1

    return {"total": total, "by_type": by_type, "traces": traces, "skipped": skipped}
