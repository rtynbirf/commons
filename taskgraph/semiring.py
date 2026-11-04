# -*- coding: utf-8 -*-
"""Полукольца пропагатора — единая алгебра всех функций структуры (SPEC-0011).

Одно ядро `taskgraph.sweep.sweep` считает любую функцию структуры плана,
если задано полукольцо S = (носитель, ⊕, ⊗, 0, 1). Каждое полукольцо здесь —
именованный проверяемый объект; реестр REGISTRY — источник по имени.
Синтез мировых практик (замер 2026-11-04): GraphBLAS — semiring как
стандарт графалгоритмики; Mohri — shortest-distance в произвольном
полукольце; Höfner/Möller «Dijkstra, Floyd and Warshall meet Kleene» —
одна алгебра на все классические алгоритмы.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable as Fn

INF = math.inf
NINF = -math.inf


@dataclass(frozen=True)
class Semiring:
    """S = (носитель неявно типами значений, ⊕=plus, ⊗=times, 0=zero, 1=one)."""

    name: str
    zero: object
    one: object
    plus: Fn[[object, object], object]
    times: Fn[[object, object], object]


# --- Б(∨,∧): достижимость, циклы ------------------------------------------------

BOOL = Semiring(
    "BOOL", False, True,
    lambda a, b: a or b,
    lambda a, b: a and b,
)

# --- (max,+): расписание, критический путь, высоты ------------------------------

MAXP = Semiring(
    "MAXP", NINF, 0.0,
    max,
    lambda a, b: a + b,
)

# --- (min,+): кратчайший маршрут ------------------------------------------------

MINP = Semiring(
    "MINP", INF, 0.0,
    min,
    lambda a, b: a + b,
)

# --- (+,×): статсумма путей (число путей) ---------------------------------------

COUNT = Semiring(
    "COUNT", 0.0, 1.0,
    lambda a, b: a + b,
    lambda a, b: a * b,
)

# --- (max,×): надёжность, Viterbi-траектория ------------------------------------

VITER = Semiring(
    "VITER", 0.0, 1.0,
    max,
    lambda a, b: a * b,
)

# --- (max,min): узкое место, пропускная способность -----------------------------

BOTT = Semiring(
    "BOTT", NINF, INF,
    max,
    min,
)


# --- ℝ[z]: производящая функция путей -------------------------------------------

def pplus(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, 0.0) + v
    return {k: round(v, 12) for k, v in out.items() if abs(v) > 1e-12}


def ptimes(a: dict, b: dict) -> dict:
    out: dict = {}
    for ka, va in a.items():
        for kb, vb in b.items():
            k = round(ka + kb, 9)
            out[k] = out.get(k, 0.0) + va * vb
    return {k: round(v, 12) for k, v in out.items() if abs(v) > 1e-12}


def shift(p: dict, delta: float) -> dict:
    """Умножение на z^delta: сдвиг степеней (длительность вершины/веса ребра)."""
    return {round(k + delta, 9): v for k, v in p.items()}


POLY = Semiring("POLY", {}, {0.0: 1.0}, pplus, ptimes)


# --- Парето (время, надёжность): мультикритерий одной проходкой -----------------
# Значение — кортеж недоминируемых пар (t, r), t по возрастанию.
# Мир спрашивает «быстро или надёжно» — фронт Парето отвечает одним sweep.

def _pareto_front(pairs) -> tuple:
    best: list = []
    for t, r in sorted(pairs, key=lambda p: (p[0], -p[1])):
        if not any(bt <= t and br >= r for bt, br in best):
            best.append((t, r))
    return tuple(best)


def par_plus(a: tuple, b: tuple) -> tuple:
    return _pareto_front(list(a) + list(b))


def par_times(a: tuple, b: tuple) -> tuple:
    return _pareto_front([(ta + tb, ra * rb) for ta, ra in a for tb, rb in b])


PARETO = Semiring("PARETO", (), ((0.0, 1.0),), par_plus, par_times)


# --- (max, log-sum-exp): термодинамика расписаний -------------------------------
# K(v) = ln Σ_путей exp(β·длина): статсумма без перечисления путей.
# Тропический предел: f(β) = K/β → критический путь при β→∞ (мировая
# практика: свободная энергия / soft-min планирование).

def logsum_semiring(beta: float) -> Semiring:
    if not beta > 0:
        raise ValueError(f"beta обязана быть > 0, пришло {beta!r} — fail-closed")

    def lse(a: float, b: float) -> float:
        m = max(a, b)
        if m == NINF:
            return NINF
        return m + math.log1p(math.exp(-abs(a - b)))

    return Semiring(
        f"LOGSUM(beta={beta:g})", NINF, 0.0,
        lse,
        lambda a, b: a + b,
    )


REGISTRY = {s.name: s for s in (BOOL, MAXP, MINP, COUNT, VITER, BOTT, POLY, PARETO)}


def by_name(name: str) -> Semiring:
    if name not in REGISTRY:
        raise ValueError(
            f"полукольцо {name!r} не в реестре {sorted(REGISTRY)} — fail-closed"
        )
    return REGISTRY[name]
