"""Журнал крови — SPEC-0003 п.4: append-only.

Переупорядочивание и удаление запрещены; всё, что записано, реконструирует сессию.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from blood.envelope import Cost, validate


class Journal:
    """Память крови. Валидирует каждый конверт до записи (SPEC-0003, отказной режим)."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._fh: Any = None

    def attach(self, path: str | Path) -> None:
        """Пишет кровь в файл в момент события (append-only, SPEC-0004 п.5).

        Открытие в режиме 'a': несколько сессий одного дня живут в одном
        файле и различаются trace_id; смерть процесса не теряет конвертов.
        """
        self._fh = open(path, "a", encoding="utf-8")

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def append(self, envelope: dict[str, Any]) -> dict[str, Any]:
        validate(envelope)
        self._events.append(dict(envelope))
        if self._fh is not None:
            self._fh.write(json.dumps(envelope, ensure_ascii=False) + "\n")
            self._fh.flush()
        return envelope

    def all(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._events)

    def by_trace(self, trace_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(e for e in self._events if e["trace_id"] == trace_id)

    def by_type(self, event_type: str) -> tuple[dict[str, Any], ...]:
        return tuple(e for e in self._events if e["type"] == event_type)

    def types(self) -> list[str]:
        return [e["type"] for e in self._events]

    def totals(self, trace_id: str | None = None) -> Cost:
        selected = self.by_trace(trace_id) if trace_id else self.all()
        total = Cost()
        for event in selected:
            total += Cost.from_dict(event["cost"])
        return total

    def to_jsonl(self, path: str | Path) -> None:
        """Снимок журнала в JSONL (порядок сохранён)."""
        Path(path).write_text(
            "\n".join(json.dumps(e, ensure_ascii=False) for e in self._events) + "\n",
            encoding="utf-8",
        )

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self._events)

    def __len__(self) -> int:
        return len(self._events)
