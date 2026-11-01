"""Приёмка слоя хранения памяти: векторный индекс (ADR-0007) и граф знаний (SPEC-0005 п.3).

Все тесты зелёные без сети и без внешних движков: базовая линия — stdlib
sqlite3 (brute-force cosine KNN) и stdlib-граф; файлы — только в tmp_path (G3).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from memory import MemoryGraph as MemoryGraphProtocol
from memory import VectorIndex, embed_text
from memory.graph import MemoryGraph
from memory.vectors import SQLiteVectorIndex


def envelope(
    source: str,
    organ: str,
    tool: str,
    trace_id: str,
    event_id: str,
    event_type: str = "act",
) -> dict[str, Any]:
    """Конверт в форме SPEC-0003 (blood/envelope.schema.json); tool — внутри payload."""
    return {
        "id": event_id,
        "ts": "2026-11-02T12:00:00.000Z",
        "type": event_type,
        "source": source,
        "organ": organ,
        "trace_id": trace_id,
        "payload": {"tool": tool},
        "cost": {"tokens_in": 1, "tokens_out": 1, "seconds": 0.1},
    }


# --- embed_text: общая база контракта (memory/__init__.py) -------------------


def test_embed_text_deterministic_normalized_and_dim() -> None:
    first = embed_text("память организма и кровь")
    second = embed_text("память организма и кровь")
    assert first == second  # детерминирован
    norm = math.sqrt(sum(x * x for x in first))
    assert math.isclose(norm, 1.0, abs_tol=1e-9)  # норма ≈ 1
    assert len(first) == 256  # длина по умолчанию


def test_embed_text_honors_custom_dim() -> None:
    assert len(embed_text("своя размерность", dim=64)) == 64


def test_embed_text_same_text_same_vector_different_text_different_vector() -> None:
    assert embed_text("граф знаний организма") == embed_text("граф знаний организма")
    assert embed_text("граф знаний организма") != embed_text("векторный индекс памяти")


# --- SQLiteVectorIndex: базовая линия ADR-0007 -------------------------------


def test_sqlite_index_implements_vector_index_protocol(tmp_path: Path) -> None:
    assert isinstance(SQLiteVectorIndex(tmp_path / "vectors.sqlite"), VectorIndex)


def test_sqlite_index_ranks_identical_text_first_with_meta(tmp_path: Path) -> None:
    index = SQLiteVectorIndex(tmp_path / "vectors.sqlite")
    assert index.count() == 0
    assert index.search([0.0, 0.0, 0.0, 0.0]) == []  # пустой индекс → []

    first = embed_text("текст про память организма")
    index.add("a", first, {"title": "память"})
    index.add("b", embed_text("совершенно посторонний текст"), {"title": "шум"})
    index.add("c", embed_text("текст про память организма"), {"title": "дубликат"})
    assert index.count() == 3

    hits = index.search(first, k=5)
    assert len(hits) == 3
    assert hits[0][0] == "a"  # первое место — сам текст (при равенстве — порядок по id)
    assert math.isclose(hits[0][1], 1.0, abs_tol=1e-9)  # сходство ≈ 1.0
    assert isinstance(hits[0][2], dict)  # meta возвращается словарём
    assert hits[0][2] == {"title": "память"}
    weights = [similarity for _, similarity, _ in hits]
    assert weights == sorted(weights, reverse=True)  # по убыванию сходства


def test_sqlite_index_replaces_on_repeated_id(tmp_path: Path) -> None:
    index = SQLiteVectorIndex(tmp_path / "vectors.sqlite")
    index.add("x", embed_text("первая запись"), {"rev": 1})
    index.add("x", embed_text("заменившая запись"), {"rev": 2})  # тот же id — замена
    assert index.count() == 1
    hits = index.search(embed_text("первая запись"), k=1)
    assert hits[0][0] == "x"
    assert hits[0][2] == {"rev": 2}


def test_sqlite_index_flush_persists_for_new_instance(tmp_path: Path) -> None:
    path = tmp_path / "vectors.sqlite"
    index = SQLiteVectorIndex(path)
    vector = embed_text("персистентность памяти")
    index.add("a", vector, {"n": 1})
    index.add("b", embed_text("фоновый шум"), {"n": 2})
    expected = index.search(vector, k=5)
    index.flush()
    index.close()
    assert path.exists()  # фактическая запись файла

    revived = SQLiteVectorIndex(path)
    assert revived.count() == 2
    assert revived.search(vector, k=5) == expected  # персистентность


# --- MemoryGraph: граф знаний SPEC-0005 п.3 ----------------------------------


def test_graph_implements_memory_graph_protocol() -> None:
    assert isinstance(MemoryGraph(), MemoryGraphProtocol)


def test_graph_builds_chain_source_organ_tool() -> None:
    graph = MemoryGraph()
    graph.add_envelope(envelope("synapse", "markitdown", "convert", "trace-1", "id-1"))
    assert graph.stats() == {"nodes": 3, "edges": 2}


def test_graph_is_idempotent_by_envelope_id() -> None:
    graph = MemoryGraph()
    envelope_once = envelope("synapse", "markitdown", "convert", "trace-1", "id-1")
    graph.add_envelope(envelope_once)
    graph.add_envelope(envelope_once)  # повтор того же конверта граф не меняет
    assert graph.stats() == {"nodes": 3, "edges": 2}
    assert graph.neighbors("organ:markitdown")[0]["weight"] == 1


def test_graph_neighbors_of_organ_include_source_and_tool() -> None:
    graph = MemoryGraph()
    graph.add_envelope(envelope("synapse", "markitdown", "convert", "trace-1", "id-1"))
    result = graph.neighbors("organ:markitdown", k=5)
    by_node = {item["node"]: item for item in result}
    assert set(by_node) == {"source:synapse", "tool:convert"}
    assert by_node["source:synapse"]["weight"] == 1
    assert by_node["tool:convert"]["weight"] == 1
    assert by_node["source:synapse"]["via"] == ["trace-1"]
    weights = [item["weight"] for item in result]
    assert weights == sorted(weights, reverse=True)  # по убыванию веса


def test_graph_accumulates_weight_and_keeps_last_three_traces() -> None:
    graph = MemoryGraph()
    for i in range(4):
        graph.add_envelope(envelope("synapse", "ollama", "generate", f"trace-{i}", f"id-{i}"))
    result = graph.neighbors("organ:ollama")
    assert len(result) == 2
    source_side = next(item for item in result if item["node"] == "source:synapse")
    assert source_side["weight"] == 4  # вес = число обменов
    assert source_side["via"] == ["trace-1", "trace-2", "trace-3"]  # не более последних 3


def test_graph_skips_organ_none_of_pid1_events() -> None:
    graph = MemoryGraph()
    graph.add_envelope(envelope("pid1", "none", "heartbeat", "trace-p1", "id-p1", "boot"))
    assert graph.stats() == {"nodes": 2, "edges": 1}  # узла organ:none нет — честно по данным
    assert [item["node"] for item in graph.neighbors("source:pid1")] == ["tool:heartbeat"]


def test_graph_flush_without_path_is_noop() -> None:
    graph = MemoryGraph()
    graph.add_envelope(envelope("synapse", "markitdown", "convert", "trace-1", "id-1"))
    graph.flush()  # нет пути — нет файла, но и нет ошибки
    assert graph.stats() == {"nodes": 3, "edges": 2}


def test_graph_flush_and_reload_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "graph.json"
    graph = MemoryGraph(path)
    graph.add_envelope(envelope("synapse", "markitdown", "convert", "trace-1", "id-1"))
    graph.add_envelope(envelope("synapse", "ollama", "generate", "trace-2", "id-2"))
    before_stats = graph.stats()
    before_neighbors = graph.neighbors("organ:markitdown")
    graph.flush()

    snapshot = json.loads(path.read_text(encoding="utf-8"))
    assert set(snapshot) == {"nodes", "edges", "seen"}
    assert snapshot["seen"] == ["id-1", "id-2"]
    assert snapshot["edges"]["source:synapse|organ:markitdown"]["weight"] == 1

    revived = MemoryGraph(path)
    assert revived.stats() == before_stats
    assert revived.neighbors("organ:markitdown") == before_neighbors
    # персистентная идемпотентность: replay тех же конвертов граф не меняет (G1)
    revived.add_envelope(envelope("synapse", "markitdown", "convert", "trace-1", "id-1"))
    assert revived.stats() == before_stats
