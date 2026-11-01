"""Граф знаний памяти — SPEC-0005 п.3: «кто с кем и чем обменивался».

Узлы — source:<имя>, organ:<имя>, tool:<имя>; ребро — обмен, вес = число
обменов, via — trace_id-ы (хранятся не более последних 3). Единственный вход —
конверт крови (SPEC-0003, blood/envelope.schema.json): поле tool живёт в
payload, organ "none" у pid1-событий узла не создаёт — честно по данным.
Память — кэш-советник, кровь — истина (SPEC-0005); только stdlib.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_MAX_VIA = 3  # на ребре хранятся не более последних 3 trace_id-ов


class MemoryGraph:
    """Граф знаний: узлы source/organ/tool, рёбра — обмены с trace_id (SPEC-0005 п.3).

    Реализует протокол MemoryGraph из memory/__init__.py. idempotent по
    envelope["id"]: повтор конверта (в том числе после перезагрузки — replay
    того же журнала крови, G1) граф не меняет. flush() при path=None — no-op
    (живой граф в теле), иначе — JSON-файл по пути конструктора (G3);
    конструктор с path читает существующий файл (персистентность).
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self._node_incoming: dict[str, int] = {}  # узел → вес входящих рёбер
        self._edges: dict[str, dict[str, Any]] = {}  # "a|b" → {"weight": int, "via": [...]}
        self._seen: dict[str, None] = {}  # id конвертов (dict — как упорядоченное множество)
        if self._path is not None and self._path.exists():
            self._load(self._path)

    def add_envelope(self, envelope: dict[str, Any]) -> None:
        """Вплетает конверт крови в граф; повтор конверта (по id) не меняет граф."""
        env_id = envelope.get("id")
        if env_id is not None:
            if env_id in self._seen:
                return
            self._seen[env_id] = None

        source = envelope.get("source")
        organ = envelope.get("organ")
        payload = envelope.get("payload") or {}
        tool = payload.get("tool") or envelope.get("tool")
        trace_id = envelope.get("trace_id")

        # Цепочка source→organ→tool из того, что есть; organ "none" — узла нет.
        chain: list[str] = []
        if source:
            chain.append(f"source:{source}")
        if organ and organ != "none":
            chain.append(f"organ:{organ}")
        if tool:
            chain.append(f"tool:{tool}")

        for node in chain:  # узлы существуют, даже если ребро пока одно
            self._node_incoming.setdefault(node, 0)
        for a, b in zip(chain, chain[1:]):
            self._link(a, b, trace_id)

    def neighbors(self, node: str, k: int = 5) -> list[dict[str, Any]]:
        """До k соседей узла: [{node, weight, via}] — по убыванию веса.

        Соседи ищутся по обеим сторонам рёбер (входящие и исходящие обмены);
        при равенстве веса — стабильный порядок по имени узла.
        """
        found: dict[str, dict[str, Any]] = {}
        for key, edge in self._edges.items():
            a, _, b = key.partition("|")
            if a == node:
                other = b
            elif b == node:
                other = a
            else:
                continue
            slot = found.setdefault(other, {"node": other, "weight": 0, "via": []})
            slot["weight"] += int(edge["weight"])
            for trace_id in edge["via"]:
                if trace_id in slot["via"]:
                    slot["via"].remove(trace_id)
                slot["via"].append(trace_id)
            del slot["via"][:-_MAX_VIA]
        ordered = sorted(found.values(), key=lambda item: (-item["weight"], item["node"]))
        return ordered[:k] if k > 0 else []

    def stats(self) -> dict[str, int]:
        """Анатомия графа: {nodes, edges}."""
        return {"nodes": len(self._node_incoming), "edges": len(self._edges)}

    def flush(self) -> None:
        """path=None — no-op; иначе JSON-файл: узлы, рёбра, виденные id конвертов."""
        if self._path is None:
            return
        snapshot = {
            "nodes": dict(self._node_incoming),
            "edges": {
                key: {"weight": int(edge["weight"]), "via": list(edge["via"])}
                for key, edge in self._edges.items()
            },
            "seen": list(self._seen),
        }
        self._path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def _link(self, a: str, b: str, trace_id: Any) -> None:
        """Проводит один обмен a→b: вес +1; via — до последних 3 различных trace_id."""
        edge = self._edges.setdefault(f"{a}|{b}", {"weight": 0, "via": []})
        edge["weight"] = int(edge["weight"]) + 1
        tid = str(trace_id) if trace_id else None
        if tid:
            if tid in edge["via"]:
                edge["via"].remove(tid)
            edge["via"].append(tid)
            del edge["via"][:-_MAX_VIA]
        self._node_incoming[b] = self._node_incoming.get(b, 0) + 1

    def _load(self, path: Path) -> None:
        """Читает состояние, записанное flush-ем (персистентность)."""
        data = json.loads(path.read_text(encoding="utf-8"))
        self._node_incoming = {str(k): int(v) for k, v in data.get("nodes", {}).items()}
        self._edges = {
            str(key): {
                "weight": int(raw.get("weight", 0)),
                "via": [str(tid) for tid in raw.get("via", [])],
            }
            for key, raw in data.get("edges", {}).items()
        }
        self._seen = {str(env_id): None for env_id in data.get("seen", [])}
