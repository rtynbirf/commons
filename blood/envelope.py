"""Конверт события крови — SPEC-0003.

Форма задаётся blood/envelope.schema.json (draft 2020-12).
`cost` обязателен всегда: там, где не применимо, — нули.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_PATH = Path(__file__).resolve().parent / "envelope.schema.json"


class EnvelopeError(ValueError):
    """Конверт не соответствует схеме крови."""


@dataclass(frozen=True)
class Cost:
    """Цена события: события без цены не существует (SPEC-0003 п.3)."""

    tokens_in: int = 0
    tokens_out: int = 0
    seconds: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "tokens_in": int(self.tokens_in),
            "tokens_out": int(self.tokens_out),
            "seconds": float(self.seconds),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Cost":
        data = data or {}
        return cls(
            tokens_in=int(data.get("tokens_in", 0)),
            tokens_out=int(data.get("tokens_out", 0)),
            seconds=float(data.get("seconds", 0.0)),
        )

    def __add__(self, other: "Cost") -> "Cost":
        return Cost(
            tokens_in=self.tokens_in + other.tokens_in,
            tokens_out=self.tokens_out + other.tokens_out,
            seconds=self.seconds + other.seconds,
        )


def now_utc() -> str:
    """Момент события, UTC, RFC 3339 с суффиксом Z."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_event_id() -> str:
    return str(uuid.uuid4())


def new_trace_id() -> str:
    """Идентификатор сессии/задачи (16 hex-символов, как в примере SPEC-0003)."""
    return uuid.uuid4().hex[:16]


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate(envelope: dict[str, Any], schema: dict[str, Any] | None = None) -> None:
    """Бросает EnvelopeError, если конверт не валиден по схеме крови."""
    schema = schema or load_schema()
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    errors = sorted(validator.iter_errors(envelope), key=lambda e: list(e.path))
    if errors:
        details = "; ".join(f"{list(e.path) or '<root>'}: {e.message}" for e in errors)
        raise EnvelopeError(f"конверт не валиден: {details}")


def make(
    event_type: str,
    source: str,
    organ: str,
    trace_id: str,
    payload: dict[str, Any],
    cost: Cost | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Собирает и валидирует конверт. Невалидный конверт наружу не выходит.

    `idempotency_key` (A01, SPEC-0003) — ключ идемпотентности отправителя:
    повторная доставка с тем же ключом не создаёт второе событие.
    """
    envelope = {
        "id": new_event_id(),
        "ts": now_utc(),
        "type": event_type,
        "source": source,
        "organ": organ,
        "trace_id": trace_id,
        "payload": payload or {},
        "cost": (cost or Cost()).as_dict(),
    }
    if idempotency_key is not None:
        envelope["idempotency_key"] = idempotency_key
    validate(envelope)
    return envelope
