"""Граф знаний памяти — SPEC-0005 п.3: «кто с кем и чем обменивался».

Узлы — source:<имя>, organ:<имя>, tool:<имя>; ребро — обмен, вес = число
обменов, via — trace_id-ы (хранятся не более последних 3). Единственный вход —
конверт крови (SPEC-0003, blood/envelope.schema.json): поле tool живёт в
payload, organ "none" у pid1-событий узла не создаёт — честно по данным.
Память — кэш-советник, кровь — истина (SPEC-0005); только stdlib.

Забывание (SPEC-0005 п.7, волна №27): граф ведёт per-trace счётчики конвертов
(`_trace_counts`) и per-trace веса рёбер (`_edge_traces`) — без них точное
забывание трейса невозможно, и `forget_trace` честно отвечает
OUT_OF_CONTROL, а не имитирует удаление. «Без счётчиков» — структурный
признак (None после загрузки старого файла), а не пустота: пустые счётчики
при живых рёбрах — тоже несогласованность (OUT_OF_CONTROL), пустые при
пустых рёбрах — точное знание «трейс не вплетался» (NOT_FOUND). Трейс
забывается вместе со своими подтрейсами `<trace_id>-*` (конвенция дома:
сцены и стыки называются `<трейс>-<имя>`); удаление по счётчикам точно
и переживает перезапуск (flush/load). Обмены без trace_id приписать
трейсу нельзя — они трейсовым забыванием не удаляются, граница названа
в докстринге.
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
        self._trace_counts: dict[str, int] | None = {}  # trace_id → число вплетённых конвертов (п.7); None — память до волны №27
        self._edge_traces: dict[str, dict[str, int]] = {}  # "a|b" → {trace_id: вес этого трейса}
        self._legacy_edges = False  # True — загружены рёбра без per-trace атрибуции (смешанная память)
        if self._path is not None and self._path.exists():
            self._load(self._path)

    def add_envelope(self, envelope: dict[str, Any]) -> None:
        """Вплетает конверт крови в граф; повтор конверта (по id) не меняет граф.

        При вплетении растёт per-trace счётчик (SPEC-0005 п.7): он делает
        будущее забывание трейса точным. Конверт без id нельзя отличить от
        повтора — счётчик растёт при каждом вплетении, честно по факту.
        """
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
        trace_key = str(trace_id) if trace_id else None
        if trace_key:
            if self._trace_counts is None:  # наследие ожило: счётчик начинается с этого конверта
                self._trace_counts = {}
            self._trace_counts[trace_key] = self._trace_counts.get(trace_key, 0) + 1

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

    def forget_trace(self, trace_id: str) -> dict[str, Any]:
        """Точное забывание трейса с его подтрейсами `<trace_id>-*` (SPEC-0005 п.7).

        Возможна только при per-trace счётчиках: память без счётчиков
        (написанная до волны №27) точно не забывается — OUT_OF_CONTROL,
        не имитация удаления (G1: перестроить из крови можно, «забыть
        точнее крови» — нельзя). Возвращает отчёт с точными числами.
        """
        trace = str(trace_id)
        if self._trace_counts is None or self._legacy_edges:
            return {
                "trace_id": trace,
                "exact": False,
                "status": "OUT_OF_CONTROL",
                "reason": "в графе нет per-trace счётчиков или есть рёбра без атрибуции (память, написанная до волны №27) — точное забывание невозможно; кровь — истина (G1: rebuild из крови в свежий движок)",
            }

        matched = [t for t in self._trace_counts if t == trace or t.startswith(trace + "-")]
        if not matched:
            if self._edge_traces and not self._trace_counts:
                return {
                    "trace_id": trace,
                    "exact": False,
                    "status": "OUT_OF_CONTROL",
                    "reason": "счётчики пусты при живых рёбрах — несогласованная память до волны №27; точное забывание невозможно",
                }
            return {
                "trace_id": trace,
                "exact": True,
                "status": "NOT_FOUND",
                "reason": "счётчики есть и говорят: этот трейс в граф не вплетался",
            }

        matched_set = set(matched)
        envelopes = sum(self._trace_counts[t] for t in matched)
        removed_edges = 0
        removed_weight = 0
        touched: set[str] = set()
        for key in list(self._edges):
            weights = self._edge_traces.get(key, {})
            w = sum(int(weights.get(t, 0)) for t in matched_set)
            if w <= 0:
                continue
            edge = self._edges[key]
            edge["weight"] = int(edge["weight"]) - w
            removed_weight += w
            edge["via"] = [tid for tid in edge["via"] if tid not in matched_set]
            for t in matched_set:
                weights.pop(t, None)
            a, _, b = key.partition("|")
            touched.add(a)
            touched.add(b)
            self._node_incoming[b] = max(0, self._node_incoming.get(b, 0) - w)
            if int(edge["weight"]) <= 0:
                del self._edges[key]
                self._edge_traces.pop(key, None)
                removed_edges += 1

        # Узлы, оставшиеся без единого ребра, забыты вместе с трейсом:
        # имя узла без обменов — не память.
        removed_nodes = 0
        for node in list(touched):
            alive = any(
                key.partition("|")[0] == node or key.partition("|")[2] == node
                for key in self._edges
            )
            if not alive and node in self._node_incoming:
                del self._node_incoming[node]
                removed_nodes += 1

        for t in matched:
            self._trace_counts.pop(t, None)

        return {
            "trace_id": trace,
            "exact": True,
            "status": "DELETED",
            "traces": matched,
            "envelopes": envelopes,
            "removed_edges": removed_edges,
            "removed_weight": removed_weight,
            "removed_nodes": removed_nodes,
        }

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
        """path=None — no-op; иначе JSON-файл: узлы, рёбра, счётчики трейсов, виденные id.

        Счётчики (trace_counts, веса рёбер по трейсам) пишутся аддитивно:
        старые файлы без них читаются, но точного забывания там уже нет —
        forget_trace честно ответит OUT_OF_CONTROL (SPEC-0005 п.7).
        """
        if self._path is None:
            return
        snapshot = {
            "nodes": dict(self._node_incoming),
            "edges": {
                key: {
                    "weight": int(edge["weight"]),
                    "via": list(edge["via"]),
                    "weights": dict(self._edge_traces.get(key, {})),
                }
                for key, edge in self._edges.items()
            },
            "seen": list(self._seen),
            "trace_counts": dict(self._trace_counts),
        }
        self._path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def _link(self, a: str, b: str, trace_id: Any) -> None:
        """Проводит один обмен a→b: вес +1; via — до последних 3 различных trace_id.

        Обмен без trace_id приписать трейсу нельзя: вес растёт, а в
        per-trace весах ребра он не живёт — трейсовым забыванием такие
        обмены не удаляются (граница честно названа, SPEC-0005 п.7).
        """
        key = f"{a}|{b}"
        edge = self._edges.setdefault(key, {"weight": 0, "via": []})
        edge["weight"] = int(edge["weight"]) + 1
        tid = str(trace_id) if trace_id else None
        if tid:
            if tid in edge["via"]:
                edge["via"].remove(tid)
            edge["via"].append(tid)
            del edge["via"][:-_MAX_VIA]
            traces = self._edge_traces.setdefault(key, {})
            traces[tid] = int(traces.get(tid, 0)) + 1
        self._node_incoming[b] = self._node_incoming.get(b, 0) + 1

    def _load(self, path: Path) -> None:
        """Читает состояние, записанное flush-ем (персистентность).

        Файлы до волны №27 без счётчиков читаются честно: счётчиков нет —
        точное забывание в таком графе невозможно (OUT_OF_CONTROL).
        """
        data = json.loads(path.read_text(encoding="utf-8"))
        self._node_incoming = {str(k): int(v) for k, v in data.get("nodes", {}).items()}
        self._edges = {}
        self._edge_traces = {}
        for key, raw in data.get("edges", {}).items():
            key = str(key)
            self._edges[key] = {
                "weight": int(raw.get("weight", 0)),
                "via": [str(tid) for tid in raw.get("via", [])],
            }
            self._edge_traces[key] = {
                str(t): int(w) for t, w in (raw.get("weights") or {}).items()
            }
        self._seen = {str(env_id): None for env_id in data.get("seen", [])}
        if "trace_counts" in data:
            self._trace_counts = {
                str(t): int(c) for t, c in (data.get("trace_counts") or {}).items()
            }
        else:
            self._trace_counts = None  # файл до волны №27: счётчиков нет — и это структурный факт
        self._legacy_edges = any(
            "weights" not in raw for raw in data.get("edges", {}).values()
        )
