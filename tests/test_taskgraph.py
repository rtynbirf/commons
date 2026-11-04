# -*- coding: utf-8 -*-
"""Приёмки SPEC-0011 (taskgraph): одна проходка — все функции структуры.

Факт — замером (инвариант 30 дома): каждая приёмка сверяет пропагатор
с независимым тупым перебором путей, а не с другим умным алгоритмом.
"""
from __future__ import annotations

import math
import random
import re
from pathlib import Path

import pytest

from taskgraph import (BOOL, BOTT, COUNT, MAXP, MINP, PARETO, POLY, VITER,
                       TaskGraph, by_name, closure, crash_contour, criticality,
                       free_energy, kahn, makespan, pathsum,
                       propagate_network, sweep, sweep_matrix, worldline)

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def g() -> TaskGraph:
    """Эталон SPEC-0011 — преемственность с поставкой движка (T=9, R(C)=0.5)."""
    graph = TaskGraph("Движок·самоприменение")
    for k, d, p in [("A", 1.0, .99), ("B", 2.0, .98), ("C", 1.0, .98),
                    ("D", 3.0, .90), ("E", 1.0, .99), ("F", 1.0, .98),
                    ("G", 1.0, .99)]:
        graph.add(k, dur=d, prob=p)
    graph.dep("A", "B", cost=2, cap=9)
    graph.dep("A", "C", cost=1, cap=7)
    graph.dep("B", "D", cost=1, cap=8)
    graph.dep("C", "D", w=0.5, cost=1, cap=5)
    graph.dep("C", "G", cost=5, cap=4)
    graph.dep("D", "E", cost=1, cap=6)
    graph.dep("E", "F", cost=1, cap=6)
    graph.dep("F", "G", cost=1, cap=7)
    return graph


def all_paths(graph: TaskGraph, src: str, dst: str, weight=lambda g, u, v: g.adj[u][v]):
    """Тупой перебор путей src→dst: [(сумма весов, произведение вероятностей)]."""
    out = []

    def walk(v, wsum, rprod):
        if v == dst:
            out.append((wsum, rprod))
            return
        for u2 in graph.succs(v):
            walk(u2, wsum + weight(graph, v, u2), rprod * graph.prob[u2])

    walk(src, 0.0, 1.0)
    return [(w + graph.dur[src] * 0 + graph.dur[dst] * 0, r) for w, r in out]


# --- развёртка и базовые образы -------------------------------------------------

def test_kahn_order_and_no_cycles(g):
    order, cyc = kahn(g)
    assert cyc == []
    pos = {v: i for i, v in enumerate(order)}
    assert all(pos[u] < pos[v] for u, v, _ in g.edges()), "порядок нарушает зависимости"


def test_bool_reachability(g):
    K, *_ = sweep(g, {v: v == "A" for v in g.dur}, BOOL, eps=lambda u, v, Ku: Ku)
    assert sorted(v for v in g.dur if K[v]) == ["A", "B", "C", "D", "E", "F", "G"]
    Kx, *_ = sweep(g, {v: v == "G" for v in g.dur}, BOOL, eps=lambda u, v, Ku: Ku)
    assert sorted(v for v in g.dur if Kx[v]) == ["G"], "достижимость из стока — только он"


def test_schedule_reserve_critical_path(g):
    T, Kp, Km, R, crit = makespan(g)
    assert T == 9.0, f"T={T!r}, эталон поставки — 9.0"
    assert crit == ["A", "B", "D", "E", "F", "G"], f"критический путь: {crit}"
    assert all(R[v] >= -1e-9 for v in g.dur), "резерв отрицателен — дефект dual-проходки"
    assert abs(R["C"] - 0.5) < 1e-9, f"резерв C={R['C']!r}, эталон — 0.5"
    for v in crit:
        assert abs(R[v]) < 1e-9, f"{v} на критическом пути, но R={R[v]!r}"


def test_shortest_price(g):
    KM, predm, *_ = sweep(g, {v: 0.0 if v == "A" else math.inf for v in g.dur}, MINP,
                          eps=lambda u, v, Ku: Ku + g.cost[(u, v)])
    brute = min(w for w, _ in [(sum(g.cost[(p[i], p[i + 1])] for i in range(len(p) - 1)), 0)
                               for p in _enum_paths(g, "A", "G")])
    assert KM["G"] == brute == 5.0
    assert worldline("G", predm) == ["A", "C", "D", "E", "F", "G"]


def _enum_paths(graph, src, dst):
    out = []

    def walk(v, acc):
        if v == dst:
            out.append(list(acc))
            return
        for u in graph.succs(v):
            acc.append(u)
            walk(u, acc)
            acc.pop()

    walk(src, [src])
    return out


def test_count_paths(g):
    KC, *_ = sweep(g, {v: 1.0 if v == "A" else 0.0 for v in g.dur}, COUNT,
                   eps=lambda u, v, Ku: Ku)
    assert KC["G"] == len(_enum_paths(g, "A", "G")) == 3.0


def test_viterbi_reliability(g):
    KV, predv, *_ = sweep(g, {v: 1.0 if v == "A" else 0.0 for v in g.dur}, VITER,
                          eps=lambda u, v, Ku: Ku, nu=lambda v, x: x * g.prob[v])
    brute = max(math.prod(g.prob[v] for v in p) for p in _enum_paths(g, "A", "G"))
    assert abs(KV["G"] - brute) < 1e-12
    assert abs(KV["G"] - 0.960498) < 1e-6, "эталон поставки: A→C→G = .99·.98·.99"
    assert worldline("G", predv) == ["A", "C", "G"]


def test_bottleneck(g):
    KB, predb, *_ = sweep(g, {v: math.inf if v == "A" else -math.inf for v in g.dur},
                          BOTT, eps=lambda u, v, Ku: min(Ku, g.cap[(u, v)]))
    brute = max(min(g.cap[(p[i], p[i + 1])] for i in range(len(p) - 1))
                for p in _enum_paths(g, "A", "G"))
    assert KB["G"] == brute, f"узкое место {KB['G']!r} != перебор {brute!r}"


def test_poly_generating_function(g):
    phi = {v: {g.dur[v]: 1.0} if not g.preds(v) else {} for v in g.dur}
    KP, *_ = sweep(g, phi, POLY,
                   eps=lambda u, v, Ku: {round(k + g.dur[v] + g.adj[u][v], 9): c
                                         for k, c in Ku.items()})
    lengths = sorted(sum(g.dur[v] + g.adj[p[i]][p[i + 1]] for i, v in enumerate(p[:-1]))
                     + g.dur[p[-1]] for p in _enum_paths(g, "A", "G"))
    assert sorted(KP["G"]) == [round(x, 9) for x in lengths], "P(z) не равна перебору путей"


def test_pareto_front(g):
    phi = {v: ((g.dur[v], g.prob[v]),) if not g.preds(v) else () for v in g.dur}
    KPAR, *_ = sweep(g, phi, PARETO,
                     eps=lambda u, v, Ku: tuple((t + g.dur[v] + g.adj[u][v],
                                                 r * g.prob[v]) for t, r in Ku))
    brute = []
    for p in _enum_paths(g, "A", "G"):
        t = sum(g.dur[v] for v in p) + sum(g.adj[p[i]][p[i + 1]]
                                           for i in range(len(p) - 1))
        brute.append((t, math.prod(g.prob[v] for v in p)))

    def front(pairs):
        best = []
        for t, r in sorted(pairs):
            if not any(bt <= t and br >= r for bt, br in best):
                best.append((t, r))
        return tuple(best)

    assert KPAR["G"] == front(brute), "фронт Парето не равен перебору путей"

    # отдельный случай: короткий путь ненадёжен — фронт из двух пар
    h = TaskGraph("быстро-или-надёжно")
    h.add("S", 0.0); h.add("F", 0.0, .99); h.add("Q", 0.0, .99)
    h.add("A", 1.0, .30); h.add("B", 5.0, .95)
    h.dep("S", "A"); h.dep("A", "F"); h.dep("S", "B"); h.dep("B", "F")
    h.dep("A", "Q"); h.dep("Q", "F")
    phi = {v: ((h.dur[v], h.prob[v]),) if not h.preds(v) else () for v in h.dur}
    K2, *_ = sweep(h, phi, PARETO,
                   eps=lambda u, v, Ku: tuple((t + h.dur[v], r * h.prob[v])
                                              for t, r in Ku))
    assert len(K2["F"]) >= 2, "фронт выродился: «быстро или надёжно» не видно"
    assert K2["F"][0][0] < K2["F"][-1][0], "фронт не отсортирован по времени"


# --- универсальная теорема на случайных планах ----------------------------------

def _random_dag(seed: int, n: int = 7, p_edge: float = 0.4) -> TaskGraph:
    rng = random.Random(seed)
    g = TaskGraph(f"случайный-{seed}")
    for i in range(n):
        g.add(f"v{i}", dur=rng.choice([0.0, 1.0, 2.0, 3.5]),
              prob=rng.uniform(0.5, 1.0))
    chain = False
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < p_edge:
                g.dep(f"v{i}", f"v{j}", w=rng.choice([0.0, 0.5, 1.0]))
                chain = True
    if not chain:
        g.dep("v0", "v1")
    return g


def test_universal_theorem_200_random_dags():
    """K* — единственный источник: sweep == тупой перебор путей на 200 планах."""
    for seed in range(200):
        g = _random_dag(seed)
        src = g.sources()[0]
        cases = (
            (BOOL, lambda u, v, Ku: Ku, lambda paths: True if paths else False),
            (MAXP, None, lambda paths: max(paths) if paths else float("-inf")),
            (MINP, None, lambda paths: min(paths) if paths else math.inf),
            (COUNT, lambda u, v, Ku: Ku, lambda paths: float(len(paths))),
        )
        for sr, eps, red in cases:
            phi = {v: sr.one if v == src else sr.zero for v in g.dur}
            K, *_ = sweep(g, phi, sr, eps=eps)
            for t in g.dur:
                paths = [sum(g.adj[p[i]][p[i + 1]] for i in range(len(p) - 1))
                         for p in _enum_paths(g, src, t)]
                expect = red(paths)
                assert K[t] == expect, (
                    f"seed={seed} полукольцо={sr.name} вершина={t}: "
                    f"sweep={K[t]!r} != перебор={expect!r}")


def test_sweep_matrix_equals_sweep_200_dags():
    for seed in range(200):
        g = _random_dag(seed)
        for sr, eps in ((MAXP, None), (COUNT, lambda u, v, Ku: Ku),
                        (MINP, None), (VITER, None)):
            phi = {v: sr.one if v == g.sources()[0] else sr.zero for v in g.dur}
            a, *_ = sweep(g, phi, sr, eps=eps)
            b = sweep_matrix(g, phi, sr, eps=eps)
            assert a == b, f"seed={seed} {sr.name}: matvec разошёлся с проходкой"


def test_closure_all_pairs_matches_sweep():
    for seed in range(20):
        g = _random_dag(seed, n=6)
        src = g.sources()[0]
        cl_min = closure(g, MINP, wfun=lambda u, v, w: g.cost[(u, v)])
        phi = {v: 0.0 if v == src else math.inf for v in g.dur}
        K, *_ = sweep(g, phi, MINP, eps=lambda u, v, Ku: Ku + g.cost[(u, v)])
        for t in g.dur:
            assert cl_min[(src, t)] == K[t], f"seed={seed} ({src},{t})"
        cl_bool = closure(g, BOOL, wfun=lambda u, v, w: True)
        phi_b = {v: v == src for v in g.dur}
        Kb, *_ = sweep(g, phi_b, BOOL, eps=lambda u, v, Ku: Ku)
        for t in g.dur:
            assert cl_bool[(src, t)] == Kb[t], f"seed={seed} BOOL ({src},{t})"


# --- циклы: pathsum и кольцо с усилением ----------------------------------------

def test_pathsum_loop_amplification_beta_cubed():
    c3 = TaskGraph("кольцо-3")
    for k in ("E0", "Z1", "Z2", "Z3"):
        c3.add(k, dur=1.0)
    c3.dep("E0", "Z1"); c3.dep("Z1", "Z2"); c3.dep("Z2", "Z3"); c3.dep("Z3", "Z1")
    beta = 0.5
    K, conv, it = pathsum(c3, {v: 1.0 if v == "E0" else 0.0 for v in c3.dur}, COUNT,
                          eps=lambda u, v, Ku: Ku * beta)
    assert conv, "не сошлось при усилении петли beta^3 = 0.125 < 1"
    assert abs(K["Z1"] - beta / (1 - beta ** 3)) < 1e-9, (
        f"K(Z1)={K['Z1']!r}: усиление петли обязано быть beta^L = 1/8")
    assert abs(K["Z2"] - beta ** 2 / (1 - beta ** 3)) < 1e-9


def test_pathsum_bool_converges_within_n():
    c3 = TaskGraph("кольцо-BOOL")
    for k in ("E0", "Z1", "Z2", "Z3"):
        c3.add(k)
    c3.dep("E0", "Z1"); c3.dep("Z1", "Z2"); c3.dep("Z2", "Z3"); c3.dep("Z3", "Z1")
    K, conv, it = pathsum(c3, {v: v == "E0" for v in c3.dur}, BOOL,
                          eps=lambda u, v, Ku: Ku, max_iter=10)
    assert conv and it <= 4, f"BOOL обязан сойтись за ≤ n итераций, взято {it}"
    assert K["Z1"] and K["Z2"] and K["Z3"] and K["E0"]


def test_pathsum_divergence_named():
    c1 = TaskGraph("петля-1")
    c1.add("X"); c1.add("Y")
    c1.dep("X", "Y"); c1.dep("Y", "X")
    K, conv, it = pathsum(c1, {v: 1.0 if v == "X" else 0.0 for v in c1.dur}, COUNT,
                          eps=lambda u, v, Ku: Ku * 2.0, max_iter=50)
    assert not conv, "усиление петли 2 > 1 — расходимость обязана быть названа"


# --- ячейки и покой (Radul/Sussman) ---------------------------------------------

def test_cells_quiescence_equals_sweep(g):
    phi = {v: float("-inf") for v in g.dur}
    nu = lambda v, x: g.dur[v] + max(0.0, x)  # noqa: E731
    net = propagate_network(g, phi, MAXP, nu=nu)
    K, *_ = sweep(g, phi, MAXP, nu=nu)
    assert net == K, "покой сети ячеек разошёлся с одной проходкой Кана"


def test_cells_incremental_update_after_new_dependency():
    g = TaskGraph("инкремент")
    for k, d in [("S", 0.0), ("M", 2.0), ("N", 3.0), ("F", 1.0)]:
        g.add(k, dur=d)
    g.dep("S", "M"); g.dep("M", "F"); g.dep("S", "N"); g.dep("N", "F")
    phi = {v: float("-inf") for v in g.dur}
    nu = lambda v, x: g.dur[v] + max(0.0, x)  # noqa: E731
    before = propagate_network(g, phi, MAXP, nu=nu)
    assert before["F"] == 4.0, f"покой до правки: F={before['F']!r}, обязан 4.0"
    g.dep("M", "N")  # правка плана: N теперь ждёт M
    after = propagate_network(g, phi, MAXP, nu=nu)
    assert after["N"] == 5.0 and after["F"] == 6.0, \
        f"сеть не дошла до нового покоя: {after}"


# --- fail-closed ----------------------------------------------------------------

def test_fail_closed_on_cycle():
    bad = TaskGraph("цикл")
    bad.add("X"); bad.add("Y")
    bad.dep("X", "Y"); bad.dep("Y", "X")
    with pytest.raises(ValueError, match="цикличен"):
        sweep(bad, {v: False for v in bad.dur}, BOOL, eps=lambda u, v, Ku: Ku)


def test_fail_closed_inputs(g):
    with pytest.raises(ValueError, match="не покрывает"):
        sweep(g, {"A": True}, BOOL, eps=lambda u, v, Ku: Ku)
    with pytest.raises(ValueError, match="длительность"):
        TaskGraph("x").add("A", dur=-1.0)
    h = TaskGraph("x"); h.add("A")
    with pytest.raises(ValueError, match="не объявлена"):
        h.dep("A", "Z")
    with pytest.raises(ValueError, match="не в реестре"):
        by_name("NOPE")
    with pytest.raises(ValueError, match="beta"):
        free_energy(g, 0.0)
    empty = TaskGraph("пустой")
    with pytest.raises(ValueError, match="нет ни одного пути"):
        criticality(empty)


# --- резервы, критичность, термодинамика ----------------------------------------

def test_reserves_and_criticality_on_random_plans():
    for seed in range(100):
        g = _random_dag(seed, n=6)
        T, Kp, Km, R, crit = makespan(g)
        assert all(R[v] >= -1e-9 for v in g.dur), f"seed={seed}: R<0"
        c = criticality(g)
        assert c[crit[0]] > 0, f"seed={seed}: вершина критпути без мировых линий"


def test_free_energy_monotone_down_to_critical_path(g):
    T, *_ = makespan(g)
    f1, f100 = free_energy(g, 1.0), free_energy(g, 100.0)
    assert f1 > f100, "свободная энергия обязана убывать с ростом β"
    assert abs(f100 - T) < 0.01, f"f(β→∞) обязано прийти к T={T}, пришло {f100}"
    assert abs(f1 - 9.4756) < 1e-3, "эталон поставки: f(β=1) = 9.4756"


# --- крэшинг-контур --------------------------------------------------------------

def test_crash_contour_budget_and_monotonicity(g):
    history, res = crash_contour(g, budget=5.0)
    assert res["spent"] <= 5.0 + 1e-9, "бюджет превышен — контур недобросовестен"
    Ts = [h[0] for h in history]
    assert all(a >= b - 1e-9 for a, b in zip(Ts, Ts[1:])), "T росло — жадность сломана"
    assert res["T"] < 9.0, "контур не сжал дедлайн ни на шаг"
    assert abs(res["T"] - 6.5) < 1e-9, f"итог {res['T']!r}: эталон прогона — 6.5"


def test_crash_contour_nonlocality_pair_move():
    """Тупик жадного хода — нелокальность: две параллельные ветви сжимаются парой."""
    g = TaskGraph("нелокальность")
    for k, d in [("S", 0.0), ("X", 3.0), ("Y", 3.0), ("Z", 1.0)]:
        g.add(k, dur=d)
    g.dep("S", "X", cost=1); g.dep("S", "Y", cost=1)
    g.dep("X", "Z"); g.dep("Y", "Z")
    history, res = crash_contour(g, budget=2.0, step=1.0)
    assert res["T"] == 2.0, f"парный ход обязан сжать обе ветви: T={res['T']!r}"
    assert any("S->X, S->Y" in h[2] for h in history), \
        f"парное сжатие не названо в истории: {history}"


def test_crash_contour_floor_respected():
    g = TaskGraph("пол")
    for k, d in [("S", 0.0), ("X", 1.0), ("Z", 1.0)]:
        g.add(k, dur=d)
    g.dep("S", "X", cost=1); g.dep("X", "Z")
    history, res = crash_contour(g, budget=10.0, step=0.5, floor=0.5)
    assert res["graph"].dur["X"] == 0.5, "floor нарушен — сжатие провалило нижнюю границу"


# --- текст как нерв, отключение, автопортрет ------------------------------------

def test_dot_text_portrait(g):
    dot = g.to_dot()
    assert "digraph" in dot
    for v in g.dur:
        assert f'"{v}"' in dot, f"вершина {v} молчит на автопортрете"
    for u, v, _ in g.edges():
        assert f'"{u}" -> "{v}"' in dot


def test_disconnect_test_no_core_imports():
    """G2: тест отключения — ядро дома живёт без taskgraph."""
    for pkg in ("brainstem", "synapse", "blood", "memory", "immune",
                "pipeline", "openclaw"):
        for py in (REPO_ROOT / pkg).rglob("*.py"):
            assert "taskgraph" not in py.read_text(encoding="utf-8"), \
                f"ядро дома завязалось на taskgraph: {py.relative_to(REPO_ROOT)}"
