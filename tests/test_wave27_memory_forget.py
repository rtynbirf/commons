# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмки волны №27 — Forget (A11, Ф-1.4) и обмен памятью с провенансом (A12/A13, ASI06 Ф-2.6).

Ф-1.4 (ТЗ ревизора, PR-4): забывание с обходом индексов/кэшей и отчётом
DELETED / NOT_FOUND / FAILED / OUT_OF_CONTROL. Кровь при этом не трогается
(append-only, SPEC-0005 п.6): забывает память, не организм — граница названа
в отчёте, не спрятана.

A12 (ручная правка памяти — diff при импорте) и A13 (экспорт/восстановимость):
снапшот памяти несёт провенанс каждой записи; импорт показывает diff и
fail-closed роняет записи без провенанса или с чужим словом происхождения
(ASI06 memory poisoning — Ф-2.6 ТЗ ревизора): ядовитая запись не входит
молча.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from blood.envelope import Cost, make
from blood.journal import Journal
from memory.engine import DefaultMemory
from memory.forget import forget
from memory.graph import MemoryGraph
from memory.trade import export, import_snapshot
from memory.vectors import SQLiteVectorIndex

TRACE = "wave27-test"


def _memory(tmp_path: Path) -> DefaultMemory:
    return DefaultMemory(tmp_path / "mem")


def _envelope(trace: str, what: str) -> dict:
    return make(
        "reflect",
        "brainstem",
        "echo-a",
        trace,
        {"what": what},
        Cost(),
    )


# --- A11: Forget ---


def test_forget_event_deleted_everywhere(tmp_path: Path) -> None:
    mem = _memory(tmp_path)
    e = _envelope(TRACE, "помнить и забыть")
    mem.observe(e)
    assert mem.index.count() == 1
    report = forget(mem, event_id=e["id"])
    assert report["index"]["status"] == "DELETED"
    assert mem.index.count() == 0
    assert report["graph"]["status"] in {"DELETED", "OUT_OF_CONTROL"}


def test_forget_unknown_is_not_found(tmp_path: Path) -> None:
    mem = _memory(tmp_path)
    report = forget(mem, event_id="нет-такого")
    assert report["status"] == "NOT_FOUND", report
    assert report["index"]["status"] == "NOT_FOUND"


def test_forget_trace_removes_all_trace_records(tmp_path: Path) -> None:
    mem = _memory(tmp_path)
    for i in range(3):
        mem.observe(_envelope(f"{TRACE}-{i}", f"шаг {i}"))
    assert mem.index.count() == 3
    report = forget(mem, trace_id=TRACE)
    assert report["index"]["status"] == "DELETED"
    assert mem.index.count() == 0
    assert report["index"]["removed"] == 3


def test_forget_never_touches_blood(tmp_path: Path) -> None:
    """Честная граница SPEC-0005 п.6: забывает память, не организм."""
    mem = _memory(tmp_path)
    e = _envelope(TRACE, "живёт в крови")
    mem.observe(e)
    report = forget(mem, trace_id=TRACE)
    assert report["blood"]["status"] == "OUT_OF_CONTROL"
    assert "append-only" in report["blood"]["reason"]


def test_forget_failed_is_honest(tmp_path: Path) -> None:
    mem = _memory(tmp_path)
    e = _envelope(TRACE, "сломать удаление")
    mem.observe(e)

    def _broken(*a, **kw):
        raise RuntimeError("диск умер")

    mem.index.delete = _broken  # type: ignore[method-assign]
    report = forget(mem, event_id=e["id"])
    assert report["status"] == "FAILED"
    assert "диск умер" in report["index"]["reason"]


def test_graph_forget_trace_is_exact_with_trace_counts(tmp_path: Path) -> None:
    g = MemoryGraph()
    e1 = _envelope(TRACE, "первый")
    e2 = _envelope("другой-трейс", "второй")
    g.add_envelope(e1)
    g.add_envelope(e2)
    before = dict(g.stats())
    result = g.forget_trace(TRACE)
    assert result["exact"] is True, "с per-trace счётчиками забывание графа точно"
    after = dict(g.stats())
    assert after["edges"] <= before["edges"]


def test_graph_forget_without_trace_counts_is_out_of_control(tmp_path: Path) -> None:
    g = MemoryGraph()
    e = _envelope(TRACE, "старая память без счётчиков")
    g.add_envelope(e)
    g._trace_counts = {}  # память, написанная до волны №27: счётчиков нет
    result = g.forget_trace(TRACE)
    assert result["exact"] is False and result["status"] == "OUT_OF_CONTROL"


def test_graph_persistence_keeps_trace_counts(tmp_path: Path) -> None:
    path = tmp_path / "graph.json"
    g = MemoryGraph(path)
    g.add_envelope(_envelope(TRACE, "персистентная"))
    g.flush()
    g2 = MemoryGraph(path)
    assert g2.forget_trace(TRACE)["exact"] is True, "счётчики переживают перезапуск"


# --- A12/A13 + ASI06: обмен памятью с провенансом ---


def _snapshot(tmp_path: Path, mem: DefaultMemory) -> Path:
    mem.observe(_envelope(TRACE, "для экспорта"))
    path = tmp_path / "snapshot.json"
    report = export(mem, path)
    assert report["status"] == "EXPORTED"
    return path


def test_export_carries_provenance(tmp_path: Path) -> None:
    mem = _memory(tmp_path)
    path = _snapshot(tmp_path, mem)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema"] == "commons-memory/v1"
    items = data["items"]
    assert items, "снапшот пустой — экспортировать нечего, экспорт обязан об этом сказать"
    for item in items:
        prov = item["meta"]["provenance"]
        assert prov["origin"] == "blood"
        assert prov["event_id"] == item["vec_id"]


def test_import_into_fresh_store_names_diff(tmp_path: Path) -> None:
    mem = _memory(tmp_path)
    path = _snapshot(tmp_path, mem)
    fresh = _memory(tmp_path / "fresh")
    diff = import_snapshot(fresh, path)
    assert diff["added"] == len(json.loads(path.read_text(encoding="utf-8"))["items"])
    assert diff["rejected"] == []


def test_import_is_idempotent(tmp_path: Path) -> None:
    mem = _memory(tmp_path)
    path = _snapshot(tmp_path, mem)
    fresh = _memory(tmp_path / "fresh")
    import_snapshot(fresh, path)
    again = import_snapshot(fresh, path)
    assert again["added"] == 0


def test_import_rejects_missing_provenance(tmp_path: Path) -> None:
    """ASI06: запись без провенанса не входит молча (fail-closed)."""
    mem = _memory(tmp_path)
    path = _snapshot(tmp_path, mem)
    data = json.loads(path.read_text(encoding="utf-8"))
    for item in data["items"]:
        del item["meta"]["provenance"]
    poisoned = tmp_path / "no-provenance.json"
    poisoned.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    fresh = _memory(tmp_path / "fresh")
    diff = import_snapshot(fresh, poisoned)
    assert diff["added"] == 0
    assert diff["rejected"] and "провенанса" in diff["rejected"][0]["reason"]


def test_import_rejects_unknown_origin(tmp_path: Path) -> None:
    """ASI06: чужое слово происхождения — ядовитая запись, отказ."""
    mem = _memory(tmp_path)
    path = _snapshot(tmp_path, mem)
    data = json.loads(path.read_text(encoding="utf-8"))
    for item in data["items"]:
        item["meta"]["provenance"]["origin"] = "слышал в интернете"
    poisoned = tmp_path / "poisoned.json"
    poisoned.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    fresh = _memory(tmp_path / "fresh")
    diff = import_snapshot(fresh, poisoned)
    assert diff["added"] == 0 and diff["rejected"]


def test_import_names_manual_edit_as_conflict(tmp_path: Path) -> None:
    """A12: ручная правка памяти видна — конфликт назван, не перезаписан молча."""
    mem = _memory(tmp_path)
    path = _snapshot(tmp_path, mem)
    fresh = _memory(tmp_path / "fresh")
    import_snapshot(fresh, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    item = data["items"][0]
    item["vector"] = [1.0 if x == 0 else x for x in item["vector"]]  # правка руками
    edited = tmp_path / "edited.json"
    edited.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    diff = import_snapshot(fresh, edited)
    assert diff["conflicts"], "правка обязана быть названа конфликтом"


def test_import_rejects_foreign_schema(tmp_path: Path) -> None:
    path = tmp_path / "alien.json"
    path.write_text(json.dumps({"schema": "чужой-формат", "items": []}), encoding="utf-8")
    mem = _memory(tmp_path)
    diff = import_snapshot(mem, path)
    assert diff["added"] == 0
    assert diff["rejected"] and "схемы" in diff["rejected"][0]["reason"]


def test_roundtrip_restores_memory(tmp_path: Path) -> None:
    """A13: восстановимость — экспорт → свежий стор → поиск находит."""
    mem = _memory(tmp_path)
    path = _snapshot(tmp_path, mem)
    fresh = _memory(tmp_path / "fresh")
    import_snapshot(fresh, path)
    assert fresh.index.count() == mem.index.count()
    hits = fresh.context("для экспорта", k=1)
    assert hits, "после восстановимости память ищется"
