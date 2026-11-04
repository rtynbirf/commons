# -*- coding: utf-8 -*-
"""Ядро: одна проходка — все функции структуры (SPEC-0011).

    K(v) = ν_v( φ(v) ⊕ Σ_{u→v} ε_uv(K(u)) )   в полукольце S.

Синтез мировых практик (замер 2026-11-04):
- GraphBLAS: та же проходка записана как разреженный matvec по слоям Кана
  (`sweep_matrix`) — семейство «semiring поверх матрицы»;
- Клейни/Флойд-Уоршалл: замыкание всех пар в произвольном полукольце
  (`closure`, Höfner–Möller);
- Mohri: расстояния до фикспойнта на графах с циклами (`pathsum`);
- Radul/Sussman «The Art of the Propagator»: ячейки с merge и покоем
  (`cells`, `propagate_network`) — тот же фикспойнт, инкрементальный жанр.
"""
from __future__ import annotations

from .graph import TaskGraph, kahn
from .semiring import Semiring

NINF = float("-inf")
INF = float("inf")


def _check_inputs(g: TaskGraph, phi: dict, sr: Semiring) -> None:
    missing = set(g.dur) - set(phi)
    if missing:
        raise ValueError(f"phi не покрывает вершины {sorted(missing)} — fail-closed")
    for v in g.dur:
        _ = sr.plus(sr.zero, phi[v])  # значение обязано жить в носителе


def sweep(g: TaskGraph, phi: dict, sr: Semiring, eps=None, nu=None):
    """Одна проходка в порядке Кана: K, pred, order, cycles.

    Цикл — дефект вызова: ValueError с поимёнными рёбрами (fail-closed);
    живой граф с циклами считается `pathsum`.
    """
    order, cyc = kahn(g)
    if cyc:
        raise ValueError(f"граф {g.name!r} цикличен ({len(cyc)} рёбер: "
                         f"{cyc[:3]}...) — для циклов есть pathsum")
    _check_inputs(g, phi, sr)
    K: dict = {}
    pred: dict[str, str | None] = {}
    for v in order:
        acc = phi[v]
        arg = None
        for u in g.preds(v):
            val = eps(u, v, K[u]) if eps else sr.times(K[u], g.adj[u][v])
            cand = sr.plus(acc, val)
            if cand != acc:
                acc, arg = cand, u
        K[v] = nu(v, acc) if nu else acc
        pred[v] = arg
    return K, pred, order, []


def sweep_matrix(g: TaskGraph, phi: dict, sr: Semiring, eps=None, nu=None) -> dict:
    """GraphBLAS-слой: та же развёртка как matvec b = φ ⊕ (Aᵀ ⊗ b) по слоям Кана.

    Слои строятся из порядка Кана (уровень = макс. глубина предка); на каждом
    слое вершина берёт ⊕ по входам из готовых строк разреженной матрицы.
    Эквивалентность sweep доказана приёмкой (tests/test_taskgraph.py).
    """
    order, cyc = kahn(g)
    if cyc:
        raise ValueError(f"граф {g.name!r} цикличен — matvec определён на DAG")
    _check_inputs(g, phi, sr)
    level = {}
    for v in order:
        level[v] = 0 if not g.preds(v) else 1 + max(level[u] for u in g.preds(v))
    rows: dict[str, list[tuple[str, str]]] = {v: [] for v in g.dur}
    for u in order:
        for v, w in g.adj[u].items():
            rows[v].append((u, w))
    K: dict = {}
    for lv in sorted(set(level.values())):
        for v in [x for x in order if level[x] == lv]:
            acc = phi[v]
            for u, w in rows[v]:
                val = eps(u, v, K[u]) if eps else sr.times(K[u], w)
                acc = sr.plus(acc, val)
            K[v] = nu(v, acc) if nu else acc
    return K


def closure(g: TaskGraph, sr: Semiring, wfun=None) -> dict[tuple[str, str], object]:
    """Клейни-замыкание (Флойд-Уоршалл в полукольце): d[(u,v)] для ВСЕХ пар.

    d[(u,v)] = Σ путей u→v (⊕ накоплений по ⊗-умножению носителя).
    Циклы не мешают — FW не требует ацикличности. wfun(u, v, w) переводит
    ребро в носитель (по умолчанию вес как есть; для BOOL — lambda u, v, w: True).
    """
    vs = sorted(g.dur)
    d: dict[tuple[str, str], object] = {}
    for u in vs:
        for v in vs:
            d[(u, v)] = sr.one if u == v else sr.zero
    for u, v, w in g.edges():
        weight = wfun(u, v, w) if wfun else w
        d[(u, v)] = sr.plus(d[(u, v)], sr.times(sr.one, weight))
    for k in vs:
        for i in vs:
            dik = d[(i, k)]
            if dik == sr.zero:
                continue
            for j in vs:
                cand = sr.times(dik, d[(k, j)])
                cur = d[(i, j)]
                merged = sr.plus(cur, cand)
                if merged != cur:
                    d[(i, j)] = merged
    return d


def pathsum(g: TaskGraph, phi: dict, sr: Semiring, eps=None, nu=None,
            max_iter: int = 10000):
    """Клейни-итерация до фикспойнта: графы с циклами (ряд Неймана/стоячие волны).

    Возвращает (K, converged, iters). Не сошлось за max_iter — честный
    converged=False: расходимость названа, не спрятана (усиление петли ≥ 1).
    """
    _check_inputs(g, phi, sr)
    K = {v: phi[v] for v in g.dur}
    for it in range(1, max_iter + 1):
        nxt = {}
        for v in g.dur:
            acc = phi[v]
            for u in g.preds(v):
                val = eps(u, v, K[u]) if eps else sr.times(K[u], g.adj[u][v])
                acc = sr.plus(acc, val)
            nxt[v] = nu(v, acc) if nu else acc
        if nxt == K:
            return nxt, True, it
        K = nxt
    return K, False, max_iter


class Cell:
    """Ячейка Радула/Сассмана: merge = ⊕ полукольца, не отступает назад."""

    __slots__ = ("name", "value", "sr", "changed")

    def __init__(self, name: str, value, sr: Semiring):
        self.name = name
        self.sr = sr
        self.value = value
        self.changed = False

    def merge(self, other) -> bool:
        merged = self.sr.plus(self.value, other)
        if merged != self.value:
            self.value = merged
            self.changed = True
            return True
        return False


def propagate_network(g: TaskGraph, phi: dict, sr: Semiring, eps=None, nu=None,
                      max_rounds: int = 10000) -> dict:
    """Сеть ячеек до покоя: распространители сидят на вершинах, очередь до тишь.

    Покой сети = тот же фикспойнт, что одна проходка Кана (приёмка-эквивалентность);
    жанр — инкрементальный: сеть доходит до нового покоя после правки входа.
    """
    _check_inputs(g, phi, sr)
    cells = {v: Cell(v, nu(v, phi[v]) if nu else phi[v], sr) for v in g.dur}
    queue = list(g.dur)
    rounds = 0
    while queue and rounds < max_rounds:
        rounds += 1
        nxt: list[str] = []
        for v in queue:
            payload = phi[v]
            for u in g.preds(v):
                val = eps(u, v, cells[u].value) if eps else \
                    sr.times(cells[u].value, g.adj[u][v])
                payload = sr.plus(payload, val)
            if nu:
                payload = nu(v, payload)
            if cells[v].merge(payload):
                nxt.extend(g.succs(v))
        queue = nxt
    if queue:
        raise ValueError("сеть ячеек не пришла к покою — расходимость названа")
    return {v: c.value for v, c in cells.items()}


def worldline(v: str, pred: dict) -> list[str]:
    """Мировая линия: восстановление аргументного пути по pred."""
    line = [v]
    while pred.get(v) is not None:
        v = pred[v]
        line.append(v)
    return list(reversed(line))
