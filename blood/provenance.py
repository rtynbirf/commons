"""Честное происхождение: конвенции чтения — SPEC-0003 п.10 (такт 2 волны №17).

Письмо ставит только заявленное (`envelope.make`: поле, о котором отправителю
нечего сказать, не выдумывается); чтение называет незаявленное честно:
доверие — unknown, неклассифицированное наружу — sensitive (fail-closed
наружу), время факта — UNKNOWN. Пролитая кровь v0.4–v0.6 классов не несёт —
заявки задним числом не достраиваются. Время без зоны в кровь не проходит
вовсе (fail-closed при записи) — «время без зоны = UNKNOWN» хотёлки
исполнено строже: мусорное время не попадает в кровь, неизвестное остаётся
null (A02).

С 0.16.0 (волна №27, ТЗ-1.2, A18, SPEC-0003 п.19) — источник знания и
«данные, не инструкция»: `knowledge_source` различает, откуда запись знает
(воля Человека / вывод тела / показание органа / незаявленное), а
`injection_markers` — детерминированное сито фраз-инструкций в тексте
payload. Сито — средство различимости, не гарантия: текст payload — данные
о мире всегда; тело исполняет только через страж полномочий, а не по тексту
записи. Отравленная запись различима (метаданные памяти несут provenance,
дневник помечает словами) и не исполняется.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from blood.envelope import load_schema

# Классы источника знания (SPEC-0003 п.19): незаявленное не достраивается.
KNOWLEDGE_SOURCES = ("human", "body", "organ", "unknown")

# Пометка дневника для отравленных записей (ТЗ-1.2, A18).
POISON_NOTE = "данные, не инструкция"

# Детерминированное сито фраз-инструкций (ru + en): ловит ФОРМУ повеления
# телу, не «похоже на инструкцию». Честная граница: сито не гарантия —
# текст payload всегда данные; исполнение — только через страж.
_INSTRUCTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bигнорир(уй|овать)\b", re.IGNORECASE),
    re.compile(r"\bзабудь\s+(все|правила|инструкции)\b", re.IGNORECASE),
    re.compile(r"\bудали(те)?\b", re.IGNORECASE),
    re.compile(r"\bотключи(те)?\s+(страж|защит|правил|фильтр)", re.IGNORECASE),
    re.compile(r"\bвыполни(те)?\s+(команд|скрипт|инструкц)", re.IGNORECASE),
    re.compile(r"\bignore\s+(all\s+)?(previous|prior|above)\b", re.IGNORECASE),
    re.compile(r"\b(disable|bypass)\s+(the\s+)?(guard|filter|rules)\b", re.IGNORECASE),
    re.compile(r"\b(delete|remove)\s+(the\s+)?file\b", re.IGNORECASE),
    re.compile(r"\bsystem\s*:", re.IGNORECASE),
)


@lru_cache(maxsize=1)
def trust_classes() -> frozenset[str]:
    """Словарь классов доверия — из схемы крови, без копии в коде."""
    return frozenset(load_schema()["properties"]["trust"]["enum"])


@lru_cache(maxsize=1)
def privacy_classes() -> frozenset[str]:
    """Словарь классов приватности — из схемы крови, без копии в коде."""
    return frozenset(load_schema()["properties"]["privacy"]["enum"])


def event_time(envelope: dict[str, Any]) -> str | None:
    """Момент факта (A02): заявленный `occurred_at` или None = UNKNOWN.

    Отсутствующее поле (старая кровь, конверт без заявки) и явный null — одно
    и то же честное «время события неизвестно»; фиктивная отметка не
    подставляется.
    """
    value = envelope.get("occurred_at")
    return value if isinstance(value, str) else None


def trust_of(envelope: dict[str, Any]) -> str:
    """Класс доверия содержимому; не заявлен — `unknown`.

    Читатель не принимает решений «записано, потому что тело видело» о той
    крови, которая не несёт заявки: неизвестное доверие — unknown.
    """
    value = envelope.get("trust")
    return value if value in trust_classes() else "unknown"


def privacy_of(envelope: dict[str, Any]) -> str:
    """Класс приватности; не классифицированное наружу — `sensitive`.

    Fail-closed наружу (правило п.10): конверт, который ничего не заявил о
    чувствительности, при выходе за пределы дома читается как sensitive —
    недоклассификация не может облегчить режим.
    """
    value = envelope.get("privacy")
    return value if value in privacy_classes() else "sensitive"


def knowledge_source(envelope: dict[str, Any]) -> str:
    """Откуда запись знает (SPEC-0003 п.19, ТЗ-1.2, A18) — по заявленному source.

    `pid1` — воля Человека (human); `brainstem`/`synapse` — вывод тела (body);
    `organ:<имя>` — показание органа (organ — данные о мире, не инструкция);
    всё прочее и незаявленное — unknown: незаявленное не достраивается (A02).
    """
    source = envelope.get("source")
    if source == "pid1":
        return "human"
    if source in ("brainstem", "synapse"):
        return "body"
    if isinstance(source, str) and source.startswith("organ:"):
        return "organ"
    return "unknown"


def injection_markers(text: str) -> list[str]:
    """Фразы-инструкции в тексте (детерминированное сито, SPEC-0003 п.19).

    Возвращает найденные маркеры (первые совпадения каждого паттерна);
    чистые данные — пустой список. Сито различает, не гарантирует: граница
    названа в модуле и в спеке — исполнение всегда через страж, не по тексту.
    """
    found: list[str] = []
    for pattern in _INSTRUCTION_PATTERNS:
        match = pattern.search(str(text))
        if match:
            found.append(match.group(0))
    return found


def payload_is_poisoned(envelope: dict[str, Any]) -> bool:
    """Несёт ли payload конверта фразы-инструкции (сито по строковым листьям)."""
    payload = envelope.get("payload") or {}
    return bool(injection_markers(json_text(payload)))


def json_text(value: Any) -> str:
    """Строковое представление значения для сита: строковые листья через пробел."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(json_text(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(json_text(item) for item in value)
    return ""
