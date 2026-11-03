"""Нюх крови — аномалии пролитой крови как измеримые сигналы (Ф-2.3).

SPEC-0003 п.19 (волна №26): выжимка (п.13) называет запахи окна недели —
нюх смотрит по файлу, глубже окна, и собирает всё измеримое, чем файл пахнет:

- битые строки (не разбираются как JSON);
- конверты без id, без цены, без trace_id — базовые обязательства п.3;
- отрицательная цена — конверт, которого журнал бы не пролил (схема
  запрещает минимум 0) — значит файл правлен руками мимо журнала;
- дубликаты id — подделка или дефект журнала;
- гэпы цепочки `prev_id` (п.7) и подмены содержимого `prev_sha256` (п.15)
  — через `blood.journal.verify` (копий логики нет);
- планы без причинно-связанного исполнения (A05, зерно дневника);
- открытые трейсы (последний конверт не reflect/halt) — висят без исхода;
- максимальная задержка наблюдения (stored_at − occurred_at, п.10) —
  сколько времени факт жил до того, как дом его увидел.

Честные правила: нюх только читает (байты крови не меняются — приёмка);
запах — измеримый сигнал, не оценка и не вердикт; файлов, которые не
разобрались, запахи не прячут — называют вслух.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from blood.journal import verify


def _parse(ts: Any) -> datetime | None:
    if not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _read(path: Path) -> tuple[list[dict[str, Any]], int]:
    events: list[dict[str, Any]] = []
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
            if isinstance(envelope, dict):
                events.append(envelope)
            else:
                skipped += 1
    return events, skipped


def smell(path: str | Path) -> list[str]:
    """Чем пахнет файл крови: список человекочитаемых измеримых сигналов."""
    path = Path(path)
    smells: list[str] = []
    events, skipped = _read(path)
    if not path.exists():
        return ["файла нет — нюхать нечего (названо, не спрятано)"]
    if skipped:
        smells.append(f"битых строк: {skipped}")
    if not events:
        smells.append("живых конвертов нет")
        return smells

    no_id = sum(1 for e in events if not e.get("id"))
    no_cost = sum(1 for e in events if "cost" not in e)
    no_trace = sum(1 for e in events if not e.get("trace_id"))
    if no_id:
        smells.append(f"конвертов без id: {no_id}")
    if no_cost:
        smells.append(f"конвертов без цены: {no_cost}")
    if no_trace:
        smells.append(f"конвертов без trace_id: {no_trace}")

    negative = 0
    for e in events:
        cost = e.get("cost") or {}
        if any(isinstance(v, (int, float)) and v < 0 for v in cost.values()):
            negative += 1
    if negative:
        smells.append(f"конвертов с отрицательной ценой: {negative}")

    ids = Counter(e["id"] for e in events if e.get("id"))
    dupes = sorted(i for i, n in ids.items() if n > 1)
    if dupes:
        smells.append(f"дубликатов id: {len(dupes)} ({', '.join(d[:8] for d in dupes[:3])}…)")

    report = verify(path)
    if report["gaps"]:
        smells.append(f"гэпов цепочки prev_id: {len(report['gaps'])}")
    if report["content_gaps"]:
        smells.append(f"подмен содержимого (prev_sha256): {len(report['content_gaps'])}")

    traces: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        if e.get("trace_id"):
            traces.setdefault(e["trace_id"], []).append(e)
    linked_ids = {e.get("causation_id") for e in events if e.get("type") == "act"}
    orphan_plans = 0
    open_traces = 0
    max_lag = 0.0
    for trace_events in traces.values():
        if any(e.get("type") == "plan" and e.get("id") not in linked_ids for e in trace_events):
            orphan_plans += 1
        last = trace_events[-1].get("type")
        if last not in ("reflect", "halt"):
            open_traces += 1
    if orphan_plans:
        smells.append(f"планов без причинно-связанного исполнения: {orphan_plans}")
    if open_traces:
        smells.append(f"открытых трейсов: {open_traces}")

    for e in events:
        occurred = _parse(e.get("occurred_at"))
        stored = _parse(e.get("stored_at"))
        if occurred and stored:
            lag = (stored - occurred).total_seconds()
            max_lag = max(max_lag, lag)
    if max_lag > 0:
        smells.append(f"максимальная задержка наблюдения: {max_lag:.0f} с")

    return smells


def smell_all(root: str | Path) -> dict[str, list[str]]:
    """Свип по всей пролитой крови дома: каждый файл runs/ понюхан и назван."""
    root = Path(root)
    report: dict[str, list[str]] = {}
    for path in sorted((root / "runs").glob("**/*.jsonl")):
        report[str(path.relative_to(root))] = smell(path)
    return report
