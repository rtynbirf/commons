"""Тонкий слой перевода: контракт пакета «Human Membrane» → кровь дома.

Решение Этапа 0 (runs/2026-11-03-membrane-baseline): домовой конверт несёт
честное происхождение (SPEC-0003 п.10, W-0022, волны №17: ядро — такт 1,
адаптер и конвенции чтения — такт 2), чужой контракт в дом не копируется —
файлы пакета не импортируются, провенанс — инвариант 4.

Честные границы перевода (что переносится, а что — нет):

- `event_name` → `type` дома; словарь типов берётся из схемы крови
  (house_event_types), копии в коде нет — дрейф невозможен. Неизвестный
  тип — fail-closed (ADR-0014): возвращается error-конверт с оригиналом
  в payload — знание сохранено, исполнение исключено (A17).
- `occurred_at` (string|null) → `occurred_at` дома; отсутствует или null —
  время события неизвестно (A02): конверт несёт null, не выдумывает.
- `observed_at` дома — заявка адаптера о моменте приёма (дом увидел событие,
  когда оно дошло до него); их `observed_at` — провенанс: чужое наблюдение —
  не наблюдение дома. Хронология честной записи видна в крови:
  occurred_at (факт у коллеги) ≤ observed_at (приём) ≤ stored_at (запись).
- `causation_id` пакета — строка произвольной формы → провенанс в
  `payload["membrane"]["causation_id"]`; домовое поле требует uuid
  (п.10) — чужой идентификатор не выдаётся за uuid дома.
- `stored_at`, `sequence`, `event_id`, `schema_version`, `correlation_id`,
  `cost` пакета → провенанс в `payload["membrane"]`: момент записи знает
  домовой журнал (п.10), порядок — append-only файл и цепочка `prev_id`
  (пп.4, 7), корреляция ≡ trace_id (п.10 — дом называет сессию сам), цена
  приёма — параметр `cost` (их cost другой разложки, честной конвертации
  нет).
- `trust`/`privacy` пакета → те же классы дома, только заявленное:
  незаявленное поле дома не получает (чтение: unknown / sensitive наружу —
  `blood/provenance.py`), заявленное personal/sensitive не понижается.
- `retention` не переносится: пролитая кровь валидна навсегда (п.6),
  чужая политика хранения в теле не живёт (отвергнуто волной №15).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from blood.envelope import Cost, EnvelopeError, load_schema, make, now_utc
from blood.provenance import privacy_classes, trust_classes


@lru_cache(maxsize=1)
def house_event_types() -> frozenset[str]:
    """Словарь типов дома — из схемы крови, без копии в коде.

    Схема — единственный источник: новый тип входит в кровь только через
    приёмку (ADR-0014), адаптеру отдельный словарь не нужен.
    """
    return frozenset(load_schema()["properties"]["type"]["enum"])


def import_event(
    event: dict[str, Any],
    *,
    trace_id: str,
    source: str = "membrane",
    organ: str = "self",
    cost: Cost | None = None,
) -> dict[str, Any]:
    """Импортирует событие контракта пакета «Human Membrane» в конверт дома.

    Возвращает конверт для Journal.append — запись остаётся решением
    вызывающего контура. `occurred_at` пакета переносится; отсутствует
    или null — null (A02: время неизвестно). Заявленные `trust`/`privacy`
    переносятся, незаявленные не выдумываются (чтение: unknown/sensitive).
    Неизвестный `event_name` не проходит в кровь чужим типом (ADR-0014):
    возвращается error-конверт — сохранено, не исполнено (A17).
    Бросает EnvelopeError, если заявки пакета не проходят схему дома
    (время без зоны, чужой класс trust/privacy) — fail-closed.
    """
    if not isinstance(event, dict):
        raise EnvelopeError("импорт ждёт объект события контракта пакета")

    provenance: dict[str, Any] = {"contract": "human-membrane/blood-event"}
    for field in (
        "event_id",
        "schema_version",
        "observed_at",
        "stored_at",
        "sequence",
        "correlation_id",
        "causation_id",
    ):
        if event.get(field) is not None:
            provenance[field] = event[field]
    if isinstance(event.get("cost"), dict) and event["cost"]:
        provenance["cost"] = event["cost"]

    event_name = event.get("event_name")

    kwargs: dict[str, Any] = {"observed_at": now_utc()}  # дом увидел при приёме
    occurred_at = event.get("occurred_at")
    kwargs["occurred_at"] = occurred_at if isinstance(occurred_at, str) else None
    trust = event.get("trust")
    if trust in trust_classes():
        kwargs["trust"] = trust  # незаявленное не выдумывается
    privacy = event.get("privacy")
    if privacy in privacy_classes():
        kwargs["privacy"] = privacy

    if event_name in house_event_types():
        return make(
            event_type=event_name,
            source=source,
            organ=organ,
            trace_id=trace_id,
            payload={"membrane": provenance},
            cost=cost,
            **kwargs,
        )

    # A17 (ADR-0014): неизвестное сохраняется, не исполняется — знание уходит
    # в error-конверт, чужой тип в крови не живёт. Конверт составляет дом —
    # его собственная заявка "unverified"; чувствительность наследуется:
    # пришедшее personal/sensitive не понижается приёмом.
    kwargs["trust"] = "unverified"
    return make(
        event_type="error",
        source=source,
        organ=organ,
        trace_id=trace_id,
        payload={
            "reason": "неизвестный event_name контракта пакета — сохранено, не исполнено (A17, ADR-0014)",
            "event_name": event_name if isinstance(event_name, str) else None,
            "original": event,
            "membrane": provenance,
        },
        cost=cost,
        **kwargs,
    )
