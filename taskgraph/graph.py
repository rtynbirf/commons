# -*- coding: utf-8 -*-
"""Граф задач: вершины-задачи, зависимости, развёртка Кана, зеркало, dot.

Кровь этого слоя не пишет — тело читает план как данные; инкрементальная
запись о прогоне — дело живого прогона (runs/), не библиотеки (G2, SPEC-0011).
"""
from __future__ import annotations

import math

INF = math.inf


class TaskGraph:
    """DAG задач: dur ≥ 0 (fail-closed), вероятности, цены и ёмкости рёбер."""

    def __init__(self, name: str = "план"):
        self.name = name
        self.dur: dict[str, float] = {}
        self.prob: dict[str, float] = {}
        self.adj: dict[str, dict[str, float]] = {}
        self.cost: dict[tuple[str, str], float] = {}
        self.cap: dict[tuple[str, str], float] = {}

    # -- строительство ---------------------------------------------------------

    def add(self, v: str, dur: float = 0.0, prob: float = 1.0) -> "TaskGraph":
        if v in self.dur:
            raise ValueError(f"вершина {v!r} уже есть — дубли не добавляются молча")
        if dur < 0:
            raise ValueError(f"длительность {v!r} = {dur!r} < 0 — fail-closed")
        if not 0.0 < prob <= 1.0:
            raise ValueError(f"вероятность {v!r} = {prob!r} вне (0,1] — fail-closed")
        self.dur[v] = float(dur)
        self.prob[v] = float(prob)
        self.adj.setdefault(v, {})
        return self

    def dep(self, u: str, v: str, w: float = 0.0, cost: float = 0.0,
            cap: float | None = None) -> "TaskGraph":
        if u not in self.dur or v not in self.dur:
            raise ValueError(f"ребро {u!r}->{v!r}: вершина не объявлена — fail-closed")
        if u == v:
            raise ValueError(f"петля {u!r}->{v!r} запрещена — циклы живут в pathsum")
        self.adj[u][v] = float(w)
        self.cost[(u, v)] = float(cost)
        self.cap[(u, v)] = float(INF if cap is None else cap)
        return self

    # -- проекции --------------------------------------------------------------

    def preds(self, v: str) -> list[str]:
        return [u for u in self.dur if v in self.adj[u]]

    def succs(self, v: str) -> list[str]:
        return list(self.adj[v])

    def edges(self) -> list[tuple[str, str, float]]:
        return [(u, v, w) for u, out in self.adj.items() for v, w in out.items()]

    def sources(self) -> list[str]:
        return [v for v in self.dur if not self.preds(v)]

    def sinks(self) -> list[str]:
        return [v for v in self.dur if not self.succs(v)]

    def flip(self) -> "TaskGraph":
        """Зеркало Gᵀ: тот же граф, все стрелки вспять (опережающий пропагатор)."""
        h = TaskGraph(f"{self.name}·T")
        for v in self.dur:
            h.add(v, self.dur[v], self.prob[v])
        for u, v, w in self.edges():
            h.dep(v, u, w, self.cost[(u, v)], self.cap[(u, v)])
        return h

    def subgraph(self, vs) -> "TaskGraph":
        """Композиция планов (мировая практика Taskflow: subgraph-узлы)."""
        keep = set(vs)
        h = TaskGraph(f"{self.name}·sub")
        for v in keep:
            h.add(v, self.dur[v], self.prob[v])
        for u, v, w in self.edges():
            if u in keep and v in keep:
                h.dep(u, v, w, self.cost[(u, v)], self.cap[(u, v)])
        return h

    def to_dot(self) -> str:
        """Текстовый автопортрет (тело не требует каналов — текст нерв, SPEC-0010)."""
        lines = [f'digraph "{self.name}" {{']
        for v in sorted(self.dur):
            lines.append(f'  "{v}" [label="{v} ({self.dur[v]:g})"];')
        for u, v, w in sorted(self.edges()):
            lines.append(f'  "{u}" -> "{v}" [label="{w:g}"];')
        lines.append("}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self.dur)


def kahn(g: TaskGraph) -> tuple[list[str], list[str]]:
    """Развёртка Кана: (порядок, возвратные рёбра). Пустой порядок при цикле."""
    indeg = {v: len(g.preds(v)) for v in g.dur}
    order: list[str] = [v for v in g.dur if indeg[v] == 0]
    order.sort()
    cyc: list[str] = []
    head = 0
    while head < len(order):
        u = order[head]
        head += 1
        for v in sorted(g.adj[u]):
            indeg[v] -= 1
            if indeg[v] == 0:
                order.append(v)
    if len(order) != len(g.dur):
        cyc = [f"{u}->{v}" for u, out in g.adj.items()
               for v in out if v not in set(order)]
    return order, cyc
