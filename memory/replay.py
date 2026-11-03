"""Replay памяти из крови — G1 SPEC-0005: «кровь — истина».

Гарантия G1 (SPEC-0005): пустой движок памяти, заполненный replay-ем журнала
крови, эквивалентен живой памяти. Для этого replay индексирует ровно те же
конверты, что и живой фасад: по п.1 SPEC-0005 конверт попадает в память после
REFLECT — значит, replay вплетает в граф и векторный индекс только конверты
type == "reflect". Остальные события остаются в крови (истина), но память —
производная крови, а не её копия: она хранит завершённые обмены.

Битая строка журнала (не JSON, не dict, конверт без обязательных полей) не
роняет replay: она честно попадает в счётчик `skipped`. Кровь append-only
(SPEC-0003) — мусор в ней возможен, истина — в неповреждённых конвертах.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from blood.provenance import knowledge_source, trust_of
from memory import MemoryGraph, VectorIndex, embed_text

# Базовая линия векторизации (ADR-0007): dim контракта embed_text.
_DIM = 256

# Минимум полей схемы крови (blood/envelope.schema.json), без которых конверт
# нельзя ни индексировать, ни вплести в граф.
_REQUIRED_FIELDS = ("id", "type", "source", "organ", "trace_id")

# Память хранит завершённые обмены: живой фасад наблюдает конверты после
# REFLECT (SPEC-0005 п.1) — replay обязан индексировать то же самое (G1).
_MEMORY_TYPES = frozenset({"reflect"})


def string_leaves(value: Any) -> list[str]:
    """Рекурсивно собирает строковые листья значения (dict и list — контейнеры).

    Порядок обхода устойчив: значения dict в порядке вставки, элементы list —
    по индексам. Нестроковые листья (числа, bool, None) в текст не попадают.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        leaves: list[str] = []
        for item in value.values():
            leaves.extend(string_leaves(item))
        return leaves
    if isinstance(value, (list, tuple)):
        leaves = []
        for item in value:
            leaves.extend(string_leaves(item))
        return leaves
    return []


def envelope_text(envelope: dict[str, Any]) -> str:
    """Текст конверта для векторизации — единый источник для replay и фасада.

    « ".join" из type, source, organ и всех строковых значений payload
    (вложенные dict — рекурсивно собранные строковые листья). Живой фасад
    (memory.engine.MemoryFacade) обязан считать текст тем же правилом,
    иначе replay перестанет быть эквивалентным живой памяти (G1).
    """
    parts = [
        str(envelope.get("type", "")),
        str(envelope.get("source", "")),
        str(envelope.get("organ", "")),
        *string_leaves(envelope.get("payload") or {}),
    ]
    return " ".join(parts)


def envelope_meta(envelope: dict[str, Any]) -> dict[str, Any]:
    """Метаданные вектора: type, source, trace_id + provenance записи (ТЗ-1.2).

    Отравленная/чужая запись различима читателем памяти: откуда знает
    (knowledge_source) и насколько можно верить (trust). Одна функция для
    живого фасада и replay — G1 не расходится.
    """
    return {
        "type": envelope.get("type", ""),
        "source": envelope.get("source", ""),
        "trace_id": envelope.get("trace_id", ""),
        "knowledge_source": knowledge_source(envelope),
        "trust": trust_of(envelope),
    }


def replay(path: Path, *, index: VectorIndex, graph: MemoryGraph) -> dict[str, Any]:
    """Восстанавливает память из крови (G1 SPEC-0005): граф + вектора из blood.jsonl.

    Каждый валидный конверт типа reflect отдаётся graph.add_envelope() и
    index.add() — текст вектора собирает envelope_text(), размерность — базовая
    линия контракта (dim=256). Фильтр reflect — не потеря, а согласованность:
    живая память (SPEC-0005 п.1) индексирует только конверты после REFLECT,
    и replay обязан делать то же самое, иначе G1-эквивалентность нарушается.
    Прочие валидные конверты считаются в `envelopes`, но в память не попадают.
    Битая строка (не JSON / не dict / без обязательных полей) — в `skipped`.

    Надгробия — часть истины крови (G4 SPEC-0005, ТЗ-1.1): конверт `forget`
    закрывает id записи — забытые reflect-конверты в производные не
    возвращаются (в том числе встреченные до надгробия в файле: replay
    выметает их из уже наполненной памяти). Счёт — `forgotten`.

    В конце вызывает index.flush() и graph.flush() — сохранение на диск делает
    сам replay (сессия завершена), а не живой фасад (SPEC-0005 п.1).

    Возвращает отчёт:
    {"envelopes": N, "indexed": V, "skipped": S, "forgotten": F,
     "graph": {"nodes": X, "edges": Y}}, где nodes/edges — из graph.stats().
    """
    path = Path(path)
    envelopes = 0
    indexed = 0
    skipped = 0
    forgotten = 0
    tombstones: dict[str, str] = {}  # id записи → id надгробия (порядок файла — истина)
    seen_reflect: dict[str, dict[str, Any]] = {}  # id → конверт (для честного выметания графа, G4)

    with path.open("rb") as blood:
        for raw_line in blood:
            line = raw_line.strip()
            try:
                line = line.decode("utf-8")
            except UnicodeDecodeError:
                skipped += 1  # двоичный мусор в крови — тоже битая строка, считаем честно
                continue
            if not line:
                skipped += 1  # пустая строка — тоже мусор в крови, считаем честно
                continue
            try:
                envelope = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if not isinstance(envelope, dict) or any(field not in envelope for field in _REQUIRED_FIELDS):
                skipped += 1
                continue

            envelopes += 1

            # Надгробие (ТЗ-1.1, G4): запись забыта — производные выметаются.
            if envelope["type"] == "forget":
                forgotten_id = (envelope.get("payload") or {}).get("forget")
                if isinstance(forgotten_id, str):
                    tombstones[forgotten_id] = envelope["id"]
                continue

            if envelope["type"] not in _MEMORY_TYPES:
                continue  # в кровь записан, в память не входит (SPEC-0005 п.1, G1)

            if envelope["id"] in tombstones:
                forgotten += 1
                continue  # забытая запись в производные не возвращается (G4)

            graph.add_envelope(envelope)
            index.add(envelope["id"], embed_text(envelope_text(envelope), dim=_DIM), envelope_meta(envelope))
            seen_reflect[envelope["id"]] = envelope
            indexed += 1

    # Надгробие, встреченное ПОСЛЕ конверта (порядок файла): выметаем из уже
    # наполненной памяти — итог тот же, что у живого forget (G4).
    for forgotten_id, _tombstone_id in tombstones.items():
        if forgotten_id in seen_reflect:
            index.forget(forgotten_id)
            graph.forget_envelope(seen_reflect[forgotten_id])
            forgotten += 1

    index.flush()
    graph.flush()

    return {
        "envelopes": envelopes,
        "indexed": indexed,
        "skipped": skipped,
        "forgotten": forgotten,
        "graph": dict(graph.stats()),
    }
