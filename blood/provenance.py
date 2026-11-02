"""Честное происхождение: конвенции чтения — SPEC-0003 п.10 (такт 2 волны №17).

Письмо ставит только заявленное (`envelope.make`: поле, о котором отправителю
нечего сказать, не выдумывается); чтение называет незаявленное честно:
доверие — unknown, неклассифицированное наружу — sensitive (fail-closed
наружу), время факта — UNKNOWN. Пролитая кровь v0.4–v0.6 классов не несёт —
заявки задним числом не достраиваются. Время без зоны в кровь не проходит
вовсе (fail-closed при записи) — «время без зоны = UNKNOWN» хотёлки
исполнено строже: мусорное время не попадает в кровь, неизвестное остаётся
null (A02).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from blood.envelope import load_schema


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
