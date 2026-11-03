"""Конверт события крови — SPEC-0003.

Форма задаётся blood/envelope.schema.json (draft 2020-12).
`cost` обязателен всегда: там, где не применимо, — нули.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_PATH = Path(__file__).resolve().parent / "envelope.schema.json"

# Страж «параметр не передан» для полей честного происхождения (SPEC-0003 п.9):
# None в параметре — честное значение (например occurred_at=None = «случилось,
# момент неизвестен»), отсутствие параметра — поле не пишется.
_UNSET: Any = object()


class EnvelopeError(ValueError):
    """Конверт не соответствует схеме крови."""


# Словарь классов обратимости (W-0024, SPEC-0003 п.16, SPEC-0001 п.5) — перевод
# зерна FR-05 пакета «Human Membrane», копий нет: план заявляет класс до факта,
# шлюз переносит в акт, дневник говорит по классу, компенсатор (SPEC-0001 п.6)
# необратимое честно не отменяет. Класс — заявка автора действия; незаявленное
# не достраивается (A02).
REVERSIBILITY_CLASSES = (
    "reversible",
    "compensatable",
    "partially_reversible",
    "irreversible",
    "unknown",
)

# Словарь классов внимания Человека (W-0025, SPEC-0003 п.17, SPEC-0004 п.9) —
# перевод зерна FR-09 пакета, копий нет: P0 остановка перед риском, P1 вопрос
# без безопасного дефолта, P2 отчёт, который должен быть увиден, P3 тихая
# запись. Счёт только по фактам крови — скрытой телеметрии нет.
ATTENTION_CLASSES = ("P0", "P1", "P2", "P3")


@dataclass(frozen=True)
class Cost:
    """Цена события: события без цены не существует (SPEC-0003 п.3).

    `attention` (W-0025, SPEC-0003 п.17) — обращения к вниманию Человека:
    заданный вопрос, открытое окно ожидания, поданный аварийный стоп —
    счёт только по фактам крови; скрытой поведенческой телеметрии нет.
    Поле аддитивно: старая кровь без него валидна навсегда (п.6).
    """

    tokens_in: int = 0
    tokens_out: int = 0
    seconds: float = 0.0
    attention: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "tokens_in": int(self.tokens_in),
            "tokens_out": int(self.tokens_out),
            "seconds": float(self.seconds),
            "attention": int(self.attention),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Cost":
        data = data or {}
        return cls(
            tokens_in=int(data.get("tokens_in", 0)),
            tokens_out=int(data.get("tokens_out", 0)),
            seconds=float(data.get("seconds", 0.0)),
            attention=int(data.get("attention", 0)),
        )

    def __add__(self, other: "Cost") -> "Cost":
        return Cost(
            tokens_in=self.tokens_in + other.tokens_in,
            tokens_out=self.tokens_out + other.tokens_out,
            seconds=self.seconds + other.seconds,
            attention=self.attention + other.attention,
        )


def now_utc() -> str:
    """Момент события, UTC, RFC 3339 с суффиксом Z."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def canonical_sha256(envelope: dict[str, Any]) -> str:
    """Канонический SHA-256 содержания конверта (W-0026, SPEC-0003 п.15).

    Каноническая форма — JSON без пробелов, ключи отсортированы, UTF-8:
    хэш заверяет СМЫСЛ конверта, а не байты конкретной строки файла.
    Хэш-цепочка в журнале шьёт и содержание: подмена любого конверта
    меняет его канонический хэш и роняет все ссылки на него.
    """
    canonical = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
    *,
    occurred_at: Any = _UNSET,
    observed_at: Any = _UNSET,
    causation_id: Any = _UNSET,
    trust: Any = _UNSET,
    privacy: Any = _UNSET,
    attention_class: Any = _UNSET,
    path: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Собирает и валидирует конверт. Невалидный конверт наружу не выходит.

    `idempotency_key` (A01, SPEC-0003) — ключ идемпотентности отправителя:
    повторная доставка с тем же ключом не создаёт второе событие.

    Честное происхождение (SPEC-0003 п.9, W-0022) — все параметры необязательны,
    старая кровь валидна навсегда:

    - `occurred_at` — когда случилось в мире; None = честный UNKNOWN (null);
    - `observed_at` — когда тело увидело;
    - `causation_id` — id семантического родителя (не файловая цепочка `prev_id`);
    - `trust` — unverified / verified / derived / unknown (неизвестный класс —
      fail-closed при записи, как неизвестный тип — ADR-0014);
    - `privacy` — public / internal / personal / sensitive (тоже fail-closed;
      отсутствие поля = не классифицировано, наружу такое считается sensitive).

    Внимание Человека (W-0025, SPEC-0003 п.17): `cost.attention` — обращения к
    вниманию по фактам; `attention_class` — класс траты P0–P3 (словарь —
    `ATTENTION_CLASSES`). Fail-closed (ADR-0014): неизвестный класс, внимание
    без класса и класс без внимания конверт не собирают — до крови не доходит.

    Момент записи (`stored_at`) журнал ставит сам при append — изготовитель
    конверта его не выдумывает.
    """
    cost = cost or Cost()
    if cost.attention < 0:
        raise EnvelopeError(f"внимание не бывает отрицательным: {cost.attention}")
    if attention_class is not _UNSET:
        if attention_class not in ATTENTION_CLASSES:
            raise EnvelopeError(
                f"класс внимания не понимается: {attention_class!r} (словарь: {', '.join(ATTENTION_CLASSES)})"
            )
        if cost.attention <= 0:
            raise EnvelopeError("класс внимания без потраченного внимания — обман, конверт не собирается")
    elif cost.attention > 0:
        raise EnvelopeError("внимание потрачено, класс не назван — конверт не собирается (SPEC-0003 п.17)")
    envelope = {
        "id": new_event_id(),
        "ts": now_utc(),
        "type": event_type,
        "source": source,
        "organ": organ,
        "trace_id": trace_id,
        "payload": payload or {},
        "cost": cost.as_dict(),
    }
    if idempotency_key is not None:
        envelope["idempotency_key"] = idempotency_key
    if occurred_at is not _UNSET:
        envelope["occurred_at"] = occurred_at
    if observed_at is not _UNSET:
        envelope["observed_at"] = observed_at
    if causation_id is not _UNSET:
        envelope["causation_id"] = causation_id
    if trust is not _UNSET:
        envelope["trust"] = trust
    if privacy is not _UNSET:
        envelope["privacy"] = privacy
    if attention_class is not _UNSET:
        envelope["attention_class"] = attention_class
    if path is not None:
        envelope["path"] = path
    validate(envelope)
    return envelope
