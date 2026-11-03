# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Забывание памяти — SPEC-0005 п.7 (Ф-1.4 ТЗ ревизора, PR-4, аксиома A11).

Забывает память, не организм: кровь (SPEC-0003) append-only и не трогается —
в отчёте это всегда названо честным OUT_OF_CONTROL, граница не спрятана
(переиграть прошлое нельзя, забыть производную — можно).

Каждое хранилище отчитывается одним из статусов:
- DELETED     — удалено, число названо;
- NOT_FOUND   — этого и не было (счётчики/поиск говорят честно);
- FAILED      — ошибка с причиной; дальше не идём, частичное забывание
                не маскируется под полное;
- OUT_OF_CONTROL — удалить честно нельзя, названа причина (кровь; граф без
                per-trace счётчиков; движок без права удаления).

Движок без права забывания (нет delete/delete_by_trace) — OUT_OF_CONTROL
(G2: право забывания — часть движка, не фасада). Забыть «что-нибудь»
нельзя: без event_id и trace_id — честный отказ до первой записи.

Трейс забывается вместе с подтрейсами `<trace_id>-*` — одна конвенция
в индексе и в графе (сцены и стыки называются `<трейс>-<имя>`).
"""

from __future__ import annotations

from typing import Any

_BLOOD_STATUS = "OUT_OF_CONTROL"
_BLOOD_REASON = (
    "кровь append-only (SPEC-0003): забывает память, не организм "
    "(SPEC-0005 п.6–7) — прошлое организма не переигрывается"
)


def forget(
    memory: Any,
    *,
    event_id: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Забывает событие (event_id) или трейс с подтрейсами (trace_id).

    Возвращает отчёт: {"status", "event_id", "trace_id", "index", "graph",
    "blood"}. Общий status ведёт индекс (основное хранилище), FAILED любого
    хранилища главный; подробности каждого — поимённо, не спрятаны.
    """
    if not event_id and not trace_id:
        raise ValueError(
            "забыть «что-нибудь» нельзя: назови event_id или trace_id "
            "(SPEC-0005 п.7 — честный отказ до первой записи)"
        )

    report: dict[str, Any] = {
        "event_id": event_id,
        "trace_id": trace_id,
        "blood": {"status": _BLOOD_STATUS, "reason": _BLOOD_REASON},
    }

    if event_id:
        report["index"] = _forget_index_event(memory, str(event_id))
        report["graph"] = {
            "status": "OUT_OF_CONTROL",
            "reason": (
                "граф хранит обмены (рёбра с весами), а не события: "
                "точечное забывание одного события в графе невозможно — "
                "точен forget по trace_id; кровь — истина (G1: rebuild)"
            ),
        }
    else:
        report["index"] = _forget_index_trace(memory, str(trace_id))
        report["graph"] = _forget_graph_trace(memory, str(trace_id))

    statuses = [
        report["index"]["status"],
        report["graph"]["status"],
    ]
    if "FAILED" in statuses:
        report["status"] = "FAILED"
    else:
        report["status"] = report["index"]["status"]
    return report


def _forget_index_event(memory: Any, event_id: str) -> dict[str, Any]:
    index = getattr(memory, "index", None)
    delete = getattr(index, "delete", None)
    if not callable(delete):
        return {
            "status": "OUT_OF_CONTROL",
            "reason": "движок индекса не даёт права забывания (нет delete) — G2: право забывания у движка",
        }
    try:
        removed = bool(delete(event_id))
    except Exception as exc:  # noqa: BLE001 — причина отчёту, не наружу (п.7 FAILED)
        return {"status": "FAILED", "removed": 0, "reason": f"{type(exc).__name__}: {exc}"}
    if removed:
        return {"status": "DELETED", "removed": 1}
    return {
        "status": "NOT_FOUND",
        "removed": 0,
        "reason": "записи с таким event_id в индексе не было",
    }


def _forget_index_trace(memory: Any, trace_id: str) -> dict[str, Any]:
    index = getattr(memory, "index", None)
    delete_by_trace = getattr(index, "delete_by_trace", None)
    if not callable(delete_by_trace):
        return {
            "status": "OUT_OF_CONTROL",
            "reason": "движок индекса не даёт права забывания трейса (нет delete_by_trace) — G2",
        }
    try:
        removed = int(delete_by_trace(trace_id))
    except Exception as exc:  # noqa: BLE001 — причина отчёту (п.7 FAILED)
        return {"status": "FAILED", "removed": 0, "reason": f"{type(exc).__name__}: {exc}"}
    if removed:
        return {"status": "DELETED", "removed": removed}
    return {
        "status": "NOT_FOUND",
        "removed": 0,
        "reason": "записей этого трейса (и подтрейсов `<trace_id>-*`) в индексе не было",
    }


def _forget_graph_trace(memory: Any, trace_id: str) -> dict[str, Any]:
    graph = getattr(memory, "graph", None)
    forget_trace = getattr(graph, "forget_trace", None)
    if not callable(forget_trace):
        return {
            "status": "OUT_OF_CONTROL",
            "reason": "граф без per-trace счётчиков и права забывания — точное удаление невозможно",
        }
    try:
        result = dict(forget_trace(trace_id))
    except Exception as exc:  # noqa: BLE001 — причина отчёту (п.7 FAILED)
        return {"status": "FAILED", "reason": f"{type(exc).__name__}: {exc}"}
    return result
