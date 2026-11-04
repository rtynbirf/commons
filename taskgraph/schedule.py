# -*- coding: utf-8 -*-
"""Расписание, резерв, критичность, крэшинг и термодинамика (SPEC-0011).

Всё это — не отдельные алгоритмы, а образы одного пропагатора:
K⁺ (max,+) — ранние финишы; K⁻ — тот же пропагатор на зеркале Gᵀ;
R = T − K⁺ − K⁻ + d — резерв; COUNT-проходки — плотность мировых линий
(критичность); (max, log-sum-exp) — свободная энергия плана; крэшинг —
контур ПРОПАГАТОР → градиент → сжатие → ПРОПАГАТОР (мировая практика CPM:
time-cost trade-off, PMI «Crash with confidence»).
"""
from __future__ import annotations

from .graph import TaskGraph
from .semiring import COUNT, MAXP, logsum_semiring
from .sweep import sweep, worldline


def _copy(g: TaskGraph, name_suffix: str = "·раб") -> TaskGraph:
    h = TaskGraph(g.name + name_suffix)
    for v in g.dur:
        h.add(v, g.dur[v], g.prob[v])
    for u, v, w in g.edges():
        h.dep(u, v, w, g.cost[(u, v)], g.cap[(u, v)])
    return h


def early(g: TaskGraph) -> tuple[dict, dict]:
    """Запаздывающий пропагатор K⁺: ранние финишы (nu = d + max(0, x))."""
    phi = {v: float("-inf") for v in g.dur}
    nu = lambda v, x: g.dur[v] + max(0.0, x)  # noqa: E731
    K, pred, _, _ = sweep(g, phi, MAXP, nu=nu)
    return K, pred


def late(g: TaskGraph) -> dict:
    """Опережающий пропагатор K⁻: высоты вершин (тот же алгоритм на Gᵀ)."""
    phi = {v: float("-inf") for v in g.dur}
    nu = lambda v, x: g.dur[v] + max(0.0, x)  # noqa: E731
    Km, _, _, _ = sweep(g.flip(), phi, MAXP, nu=nu)
    return Km


def makespan(g: TaskGraph):
    """(T, K⁺, K⁻, R, критический путь). R = T − K⁺ − K⁻ + d, R=0 — критика."""
    Kp, pred = early(g)
    Km = late(g)
    T = max(Kp.values())
    R = {v: T - Kp[v] - Km[v] + g.dur[v] for v in g.dur}
    crit = worldline(max(Kp, key=Kp.get), pred)
    return T, Kp, Km, R, crit


def criticality(g: TaskGraph) -> dict[str, float]:
    """Плотность мировых линий: c(v) = n⁺(v)·n⁻(v)/N (COUNT-проходки).

    n⁺ — сколько путей ведёт в v, n⁻ — сколько выходит, N — всего путей
    источник→сток. Вершины критического пути держат максимум c.
    """
    phi_plus = {v: 1.0 if not g.preds(v) else 0.0 for v in g.dur}
    eps_neutral = lambda u, v, Ku: Ku  # noqa: E731
    n_plus, _, _, _ = sweep(g, phi_plus, COUNT, eps=eps_neutral)
    gt = g.flip()
    phi_minus = {v: 1.0 if not gt.preds(v) else 0.0 for v in g.dur}
    n_minus, _, _, _ = sweep(gt, phi_minus, COUNT, eps=eps_neutral)
    total = sum(n_plus[v] for v in g.sinks())
    if total == 0:
        raise ValueError("в графе нет ни одного пути источник→сток — fail-closed")
    return {v: n_plus[v] * n_minus[v] / total for v in g.dur}


def free_energy(g: TaskGraph, beta: float) -> float:
    """Свободная энергия плана f(β) = (1/β)·ln Σ_путей exp(β·длина).

    β→∞ — тропический предел, f → T (критический путь = основное состояние);
    меньшие β — ансамбль всех путей с больцмановскими весами.
    """
    sr = logsum_semiring(beta)
    phi = {v: beta * g.dur[v] if not g.preds(v) else float("-inf") for v in g.dur}
    eps = lambda u, v, Ku: Ku + beta * (g.dur[v] + g.adj[u][v])  # noqa: E731
    K, _, _, _ = sweep(g, phi, sr, eps=eps)
    return max(K[v] for v in g.sinks()) / beta


def _apply_crash(g: TaskGraph, edge: tuple[str, str], delta: float) -> None:
    """Сжатие: длительность головы ребра уходит вниз на delta (не ниже нуля)."""
    g.dur[edge[1]] = max(0.0, g.dur[edge[1]] - delta)


def crash_contour(g: TaskGraph, budget: float, step: float = 0.5,
                  floor: float | None = None):
    """Крэшинг-контур: ПРОПАГАТОР → градиент → сжатие → ПРОПАГАТОР.

    Жадный ход сжимает самое дешёвое ребро критического пути (cost slope —
    мировая практика CPM); тупик жадного хода — нелокальность: T держит
    параллельная ветвь, и сжать надо пару независимых ходов. План вызывающего
    не портится: контур работает на копии. Возвращает (история, итог), где
    история — [(T_до, потрачено, что случилось)], итог — {T, spent, crit, graph}.
    """
    if budget < 0 or step <= 0:
        raise ValueError("бюджет < 0 или шаг ≤ 0 — дефект вызова, fail-closed")
    floor = 0.0 if floor is None else floor
    work = _copy(g)
    spent = 0.0
    history: list[tuple[float, float, str]] = []
    while spent < budget:
        T, Kp, Km, R, _ = makespan(work)
        crit_verts = {v for v in work.dur if abs(R[v]) < 1e-9}
        cand = []
        for (u, v) in sorted(work.cost):
            if u in crit_verts and v in crit_verts:
                room = work.dur[v] - floor
                if room + 1e-12 >= step:
                    cand.append((work.cost[(u, v)] / step, (u, v)))
        if not cand:
            history.append((T, spent, "тупик: критических ходов нет"))
            break
        cand.sort()
        _, best = cand[0]
        # Проба жадного хода на копии: двигает ли он T?
        trial = _copy(work, "·проба")
        _apply_crash(trial, best, step)
        T_trial, *_ = makespan(trial)
        moves = [best]
        if T_trial >= T - 1e-12:
            # Тупик жадного хода — нелокальность: ищем парный ход по ветви
            found = False
            for _, second in cand:
                if second == best:
                    continue
                trial2 = _copy(trial, "·пара")
                _apply_crash(trial2, second, step)
                T2, *_ = makespan(trial2)
                if T2 < T_trial - 1e-12:
                    moves = [best, second]
                    found = True
                    break
            if not found:
                history.append((T, spent, "тупик: парного хода нет"))
                break
        price = sum(work.cost[e] for e in moves)
        if spent + price > budget:
            history.append((T, spent,
                            f"бюджет: ход {['%s->%s' % e for e in moves]} "
                            f"стоит {price:g} > остатка {budget - spent:g}"))
            break
        for e in moves:
            _apply_crash(work, e, step)
        spent += price
        history.append((T, spent,
                        "сжато: " + ", ".join(f"{u}->{v}" for u, v in moves)))
    T_final, _, _, _, crit = makespan(work)
    return history, {"T": T_final, "spent": spent, "crit": crit, "graph": work}


def compact_report(g: TaskGraph) -> dict:
    """Одно слово на вопрос организма: сроки, резервы, критика, энергия."""
    T, Kp, Km, R, crit = makespan(g)
    return {
        "T": T,
        "reserve": {v: R[v] for v in sorted(g.dur)},
        "critical_path": crit,
        "criticality": criticality(g),
        "f_beta_1": free_energy(g, 1.0),
        "f_beta_100": free_energy(g, 100.0),
    }
