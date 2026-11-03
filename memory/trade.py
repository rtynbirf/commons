# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Обмен памятью со снапшотом-провенансом — SPEC-0005 п.8 (Ф-1.4, A12/A13, ASI06 Ф-2.6).

Экспорт: снапшот схемы `commons-memory/v1` — каждая запись несёт вектор и
провенанс (origin «blood», event_id — id конверта): память производна от крови,
и снапшот говорит, откуда что взялось.

Импорт fail-closed (ADR-0014):
- запись без провенанса или с чужим словом происхождения — rejected:
  ядовитая запись не входит молча (ASI06 memory poisoning);
- чужая схема — rejected целиком;
- ручная правка уже существующей записи — конфликт назван поимённо,
  не перезаписан молча (A12);
- повторный импорт того же снапшота не повторяет эффект (added = 0);
- импорт в свежее хранилище восстанавливает поиск (A13).

Снапшот — локальный файл по явному пути (G3): память не покидает машину сама.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA = "commons-memory/v1"
BLOOD_ORIGIN = "blood"


def export(memory: Any, path: Path | str) -> dict[str, Any]:
    """Выгружает память в снапшот с провенансом каждой записи (A13)."""
    path = Path(path)
    index = getattr(memory, "index", None)
    items_fn = getattr(index, "items", None)
    if not callable(items_fn):
        return {
            "status": "OUT_OF_CONTROL",
            "reason": "движок индекса не даёт выгрузки (нет items) — экспорт невозможен честно, не имитируется",
        }
    items: list[dict[str, Any]] = []
    for vec_id, vector, meta in items_fn():
        item_meta = dict(meta or {})
        item_meta.setdefault("provenance", {"origin": BLOOD_ORIGIN, "event_id": vec_id})
        items.append({"vec_id": vec_id, "vector": vector, "meta": item_meta})
    snapshot = {"schema": SCHEMA, "items": items}
    path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"status": "EXPORTED", "path": str(path), "items": len(items)}


def import_snapshot(
    memory: Any,
    path: Path | str,
    *,
    tombstoned: set[str] | None = None,
) -> dict[str, Any]:
    """Импортирует снапшот fail-closed; возвращает diff: added/skipped/rejected/conflicts.

    Надгробия (G4, стык 0.48.2): запись, на которую в крови висит forget-надгробие
    (SPEC-0003 п.18), не возвращается в производные — импорт не оживляет забытое.
    Надгробия передаются множеством id (`tombstoned`, из крови: тип forget →
    payload["forget"]); None — импорт не сверялся с кровью, и отчёт называет это
    честно (tombstones_checked: false), не выдаёт молчание за сверку.
    """
    path = Path(path)
    result: dict[str, Any] = {
        "path": str(path),
        "schema": None,
        "added": 0,
        "skipped": 0,
        "skipped_tombstoned": [] if tombstoned is not None else None,
        "tombstones_checked": tombstoned is not None,
        "rejected": [],
        "conflicts": [],
    }

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — нечитаемый снапшот назван, не проглочен
        result["rejected"].append(
            {"vec_id": None, "reason": f"снапшот не читается: {type(exc).__name__}: {exc}"}
        )
        return result

    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        found = data.get("schema") if isinstance(data, dict) else type(data).__name__
        result["rejected"].append(
            {
                "vec_id": None,
                "reason": (
                    f"снапшот другой схемы ({found!r}): ожидалась {SCHEMA} — "
                    "чужой формат не входит молча (fail-closed, ASI06)"
                ),
            }
        )
        return result
    result["schema"] = SCHEMA

    index = getattr(memory, "index", None)
    add = getattr(index, "add", None)
    get = getattr(index, "get", None)
    if not callable(add):
        result["rejected"].append(
            {"vec_id": None, "reason": "движок индекса не даёт записи (нет add) — импорт невозможен честно"}
        )
        return result

    items = data.get("items")
    if not isinstance(items, list):
        result["rejected"].append(
            {"vec_id": None, "reason": "в снапшоте нет списка items: форма не та — не вхожу молча"}
        )
        return result

    for item in items:
        if not isinstance(item, dict):
            result["rejected"].append({"vec_id": None, "reason": "запись не словарь: форма не та"})
            continue
        vec_id = item.get("vec_id")
        vector = item.get("vector")
        meta = item.get("meta")
        provenance = meta.get("provenance") if isinstance(meta, dict) else None

        if tombstoned is not None and isinstance(vec_id, str) and vec_id in tombstoned:
            result["skipped_tombstoned"].append(vec_id)  # забытое не оживает (G4)
            continue

        if not isinstance(provenance, dict) or not provenance.get("origin") or not provenance.get("event_id"):
            result["rejected"].append(
                {
                    "vec_id": vec_id,
                    "reason": "запись без провенанса: происхождение не названо — ядовитая запись не входит молча (ASI06)",
                }
            )
            continue
        if provenance.get("origin") != BLOOD_ORIGIN or provenance.get("event_id") != vec_id:
            result["rejected"].append(
                {
                    "vec_id": vec_id,
                    "reason": (
                        f"чужое слово происхождения ({provenance.get('origin')!r}): память "
                        f"производна только от крови ({BLOOD_ORIGIN!r}, SPEC-0005) — не вхожу молча (ASI06)"
                    ),
                }
            )
            continue
        if not isinstance(vec_id, str) or not vec_id or not _is_vector(vector):
            result["rejected"].append(
                {"vec_id": vec_id, "reason": "запись без вменяемого vec_id/вектора: форма не та"}
            )
            continue

        existing = get(vec_id) if callable(get) else None
        if existing is not None:
            old_vector, old_meta = existing
            if old_vector == vector and old_meta == meta:
                result["skipped"] += 1  # повторная доставка — эффект не повторяется
            else:
                result["conflicts"].append(
                    {
                        "vec_id": vec_id,
                        "reason": "запись уже есть и отличается: правка названа, не перезаписана молча (A12)",
                        "diff": _diff(old_vector, old_meta, vector, meta),
                    }
                )
            continue

        add(vec_id, vector, meta)
        result["added"] += 1

    flush = getattr(index, "flush", None)
    if callable(flush):
        flush()  # фактическая запись файла — сам импорт (как replay, G1)
    return result


def _is_vector(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in value)


def _diff(old_vector: Any, old_meta: Any, new_vector: Any, new_meta: Any) -> dict[str, Any]:
    return {
        "vector_changed": old_vector != new_vector,
        "meta_changed": old_meta != new_meta,
    }
