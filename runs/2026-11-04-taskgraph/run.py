# -*- coding: utf-8 -*-
# Живой прогон волны №32 (план числом: SPEC-0011, ADR-0018, хотёлка W-0037).
# Дата: 2026-11-04. Красный факт зафиксирован: пакет taskgraph спрятан —
# сюит краснеет сборкой (1 error during collection, ModuleNotFoundError:
# taskgraph); пакет возвращён — 26 passed. Граница названа: код родился
# раньше приёмок, порядок воли «красный → чинка → зелёный» не соблюдён.
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, seal, verify  # noqa: E402
from taskgraph import (BOOL, COUNT, MAXP, MINP, PARETO, POLY, VITER, TaskGraph,  # noqa: E402
                       closure, crash_contour, criticality, free_energy,
                       makespan, pathsum, propagate_network, sweep, sweep_matrix)

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
TRACE = "wave32-taskgraph"

if JOURNAL.exists():
    raise SystemExit(
        "кровь прогона уже пролита и запечатана — прогон не переписывает свою кровь молча "
        "(косяк двойного запуска пойман живьём 2026-11-03); "
        "осознанный повтор — удалить blood.jsonl руками, назвав причину"
    )

journal = Journal()
journal.attach(JOURNAL)
results: dict[str, dict] = {}


def stamp(event_type: str, payload: dict, key: str, seconds: float = 0.0) -> None:
    journal.append(make(event_type, "taskgraph", "self", TRACE, payload,
                        Cost(0, 0, round(seconds, 6)), idempotency_key=key))


# --- эталонный план (преемственность с поставкой движка) ------------------------

g = TaskGraph("Движок·самоприменение")
for k, d, p in [("A", 1.0, .99), ("B", 2.0, .98), ("C", 1.0, .98),
                ("D", 3.0, .90), ("E", 1.0, .99), ("F", 1.0, .98),
                ("G", 1.0, .99)]:
    g.add(k, dur=d, prob=p)
g.dep("A", "B", cost=2, cap=9)
g.dep("A", "C", cost=1, cap=7)
g.dep("B", "D", cost=1, cap=8)
g.dep("C", "D", w=0.5, cost=1, cap=5)
g.dep("C", "G", cost=5, cap=4)
g.dep("D", "E", cost=1, cap=6)
g.dep("E", "F", cost=1, cap=6)
g.dep("F", "G", cost=1, cap=7)

# --- [1] расписание: T, резервы, критический путь -------------------------------

t0 = time.monotonic()
T, Kp, Km, R, crit = makespan(g)
elapsed = time.monotonic() - t0
assert T == 9.0 and crit == ["A", "B", "D", "E", "F", "G"]
assert abs(R["C"] - 0.5) < 1e-9 and all(R[v] >= -1e-9 for v in g.dur)
results["schedule"] = {"T": T, "reserve": {k: R[k] for k in sorted(R)}, "crit": crit}
stamp("act", {"step": "makespan", "T": T, "reserve": {k: R[k] for k in sorted(R)},
              "critical_path": crit,
              "honesty": "резерв из одного пропагатора на зеркале Gᵀ, не второй алгоритм"},
      "tg-1-makespan", elapsed)

# --- [2] статсумма, надёжность, производящая функция, Парето --------------------

t0 = time.monotonic()
KC, *_ = sweep(g, {v: 1.0 if v == "A" else 0.0 for v in g.dur}, COUNT,
               eps=lambda u, v, Ku: Ku)
KV, predv, *_ = sweep(g, {v: 1.0 if v == "A" else 0.0 for v in g.dur}, VITER,
                      eps=lambda u, v, Ku: Ku, nu=lambda v, x: x * g.prob[v])
phi_poly = {v: {g.dur[v]: 1.0} if not g.preds(v) else {} for v in g.dur}
KP, *_ = sweep(g, phi_poly, POLY,
               eps=lambda u, v, Ku: {round(k + g.dur[v] + g.adj[u][v], 9): c
                                     for k, c in Ku.items()})
phi_par = {v: ((g.dur[v], g.prob[v]),) if not g.preds(v) else () for v in g.dur}
KPAR, *_ = sweep(g, phi_par, PARETO,
                 eps=lambda u, v, Ku: tuple((t + g.dur[v] + g.adj[u][v], r * g.prob[v])
                                            for t, r in Ku))
elapsed = time.monotonic() - t0
assert KC["G"] == 3.0 and abs(KV["G"] - 0.960498) < 1e-6
assert sorted(KP["G"]) == [3.0, 8.5, 9.0]
results["paths"] = {"count": KC["G"], "reliability": round(KV["G"], 6),
                    "viterbi_route": "A→C→G",
                    "P(z)": KP["G"], "pareto_front": [(t, round(r, 6)) for t, r in KPAR["G"]]}
stamp("act", {"step": "path_ensemble", **results["paths"],
              "honesty": "четыре вопроса — одна проходка, четыре полукольца"},
      "tg-2-paths", elapsed)

# --- [3] критичность: плотность мировых линий -----------------------------------

t0 = time.monotonic()
c = criticality(g)
elapsed = time.monotonic() - t0
assert abs(c["A"] - 1.0) < 1e-9 and abs(c["G"] - 1.0) < 1e-9
results["criticality"] = {k: round(v, 3) for k, v in sorted(c.items())}
stamp("act", {"step": "criticality", "density": results["criticality"],
              "honesty": "c(v) = n⁺(v)·n⁻(v)/N — градиент ∂T/∂d, плотность мировых линий"},
      "tg-3-criticality", elapsed)

# --- [4] термодинамика: свободная энергия ---------------------------------------

t0 = time.monotonic()
f1, f10, f100 = free_energy(g, 1.0), free_energy(g, 10.0), free_energy(g, 100.0)
elapsed = time.monotonic() - t0
assert f1 > f10 > f100 and abs(f100 - T) < 0.01 and abs(f1 - 9.4756) < 1e-3
results["thermodynamics"] = {"f_beta_1": round(f1, 4), "f_beta_10": round(f10, 4),
                             "f_beta_100": round(f100, 4), "T": T}
stamp("act", {"step": "free_energy", **results["thermodynamics"],
              "honesty": "тропический предел: критический путь — основное состояние ансамбля путей"},
      "tg-4-free-energy", elapsed)

# --- [5] крэшинг-контур: бюджет 5.0 ---------------------------------------------

t0 = time.monotonic()
history, res = crash_contour(g, budget=5.0)
elapsed = time.monotonic() - t0
assert res["spent"] <= 5.0 + 1e-9 and res["T"] < 9.0
results["crash"] = {"T_final": res["T"], "spent": res["spent"],
                    "history": [f"{h[0]:g} → {h[2]}" for h in history]}
stamp("act", {"step": "crash_contour", "T_final": res["T"], "spent": res["spent"],
              "moves": [h[2] for h in history],
              "honesty": "контур на копии; бюджет — жёсткий потолок; ходы названы"},
      "tg-5-crash", elapsed)

# --- [6] эквивалентности трёх жанров и замыкания --------------------------------

t0 = time.monotonic()
phi_max = {v: float("-inf") for v in g.dur}
nu_dur = lambda v, x: g.dur[v] + max(0.0, x)  # noqa: E731
K_sweep, *_ = sweep(g, phi_max, MAXP, nu=nu_dur)
K_matrix = sweep_matrix(g, phi_max, MAXP, nu=nu_dur)
K_cells = propagate_network(g, phi_max, MAXP, nu=nu_dur)
cl_min = closure(g, MINP, wfun=lambda u, v, w: g.cost[(u, v)])
KM, *_ = sweep(g, {v: 0.0 if v == "A" else math.inf for v in g.dur}, MINP,
               eps=lambda u, v, Ku: Ku + g.cost[(u, v)])
elapsed = time.monotonic() - t0
assert K_matrix == K_sweep == K_cells and cl_min[("A", "G")] == KM["G"] == 5.0
results["equivalences"] = {"sweep_matrix_eq": True, "cells_eq": True,
                           "closure_min_price_A_G": cl_min[("A", "G")]}
stamp("act", {"step": "equivalences", **results["equivalences"],
              "honesty": "Кан = matvec (GraphBLAS) = покой ячеек (Radul/Sussman); Клейни-замыкание = sweep"},
      "tg-6-equivalences", elapsed)

# --- [7] кольцо: усиление петли β³ ----------------------------------------------

t0 = time.monotonic()
c3 = TaskGraph("кольцо-3")
for k in ("E0", "Z1", "Z2", "Z3"):
    c3.add(k, dur=1.0)
c3.dep("E0", "Z1"); c3.dep("Z1", "Z2"); c3.dep("Z2", "Z3"); c3.dep("Z3", "Z1")
Kc, conv, iters = pathsum(c3, {v: 1.0 if v == "E0" else 0.0 for v in c3.dur}, COUNT,
                          eps=lambda u, v, Ku: Ku * 0.5)
elapsed = time.monotonic() - t0
assert conv and abs(Kc["Z1"] - 0.5 / (1 - 0.125)) < 1e-9
results["loop"] = {"K_Z1": round(Kc["Z1"], 6), "theory": round(0.5 / (1 - 0.125), 6),
                   "iters": iters}
stamp("act", {"step": "pathsum_loop", **results["loop"],
              "honesty": "усиление петли β^L = 1/8, не β; расходимость при β ≥ 1 названа честным converged=False"},
      "tg-7-loop", elapsed)

# --- [8] универсальная теорема на 200 случайных планах ---------------------------

t0 = time.monotonic()
import random  # noqa: E402

checked = 0
for seed in range(200):
    rng = random.Random(seed)
    h = TaskGraph(f"random-{seed}")
    for i in range(7):
        h.add(f"v{i}", dur=rng.choice([0.0, 1.0, 2.0, 3.5]), prob=rng.uniform(0.5, 1.0))
    chain = False
    for i in range(7):
        for j in range(i + 1, 7):
            if rng.random() < 0.4:
                h.dep(f"v{i}", f"v{j}", w=rng.choice([0.0, 0.5, 1.0]))
                chain = True
    if not chain:
        h.dep("v0", "v1")
    src = h.sources()[0]
    for sr, eps, red in ((BOOL, lambda u, v, Ku: Ku, lambda ps: bool(ps)),
                         (MAXP, None, lambda ps: max(ps) if ps else float("-inf")),
                         (MINP, None, lambda ps: min(ps) if ps else math.inf),
                         (COUNT, lambda u, v, Ku: Ku, lambda ps: float(len(ps)))):
        phi = {v: sr.one if v == src else sr.zero for v in h.dur}
        K, *_ = sweep(h, phi, sr, eps=eps)
        for t in h.dur:
            paths = []

            def walk(v, acc, t=t):
                if v == t:
                    paths.append(sum(h.adj[acc[i]][acc[i + 1]] for i in range(len(acc) - 1)))
                    return
                for u in h.succs(v):
                    walk(u, acc + [u])

            walk(src, [src])
            assert K[t] == red(paths), (seed, sr.name, t)
            checked += 1
elapsed = time.monotonic() - t0
results["universal_theorem"] = {"random_plans": 200, "semirings": 4, "checks": checked,
                                "mismatches": 0}
stamp("act", {"step": "universal_theorem", **results["universal_theorem"],
              "honesty": "сверка с тупым перебором путей — факт, не другой умный алгоритм"},
      "tg-8-universal", elapsed)

# --- [9] тест отключения (G2) ---------------------------------------------------

t0 = time.monotonic()
core_hits = 0
for pkg in ("brainstem", "synapse", "blood", "memory", "immune", "pipeline", "openclaw"):
    for py in (REPO_ROOT / pkg).rglob("*.py"):
        if "taskgraph" in py.read_text(encoding="utf-8"):
            core_hits += 1
elapsed = time.monotonic() - t0
assert core_hits == 0
results["disconnect_test"] = {"core_imports_of_taskgraph": 0}
stamp("act", {"step": "disconnect_test", **results["disconnect_test"],
              "honesty": "G2: пакет выдёргивается без правок тела"},
      "tg-9-disconnect", elapsed)

# --- итог ------------------------------------------------------------------------

journal.append(make(
    "reflect",
    "taskgraph",
    "self",
    TRACE,
    {
        "verdict": "ok",
        "criterion": "26 приёмок tests/test_taskgraph.py + 9 актов этого прогона с ассертами",
        "summary": "одна проходка — все функции структуры: план организма отвечает числом",
        "honesty": "порядок воли не соблюдён: код родился раньше приёмок; красный факт воспроизведён "
                   "демонстрацией (пакет спрятан — collection error ModuleNotFoundError: taskgraph); "
                   "косяки пойманы живыми прогонами и названы в report.md",
        "next": "MCP-синапс для вызовов плана из PLAN (ритуал ADR-0005) — по слову Человека",
        "facts": results,
    },
    Cost(0, 0, 0.0),
    idempotency_key="wave32-reflect",
))

journal.close()
report = verify(JOURNAL)
print(json.dumps(report, ensure_ascii=False))
assert report["gaps"] == [] and not report.get("content_gaps")

rel = str(JOURNAL.relative_to(REPO_ROOT))
anchor = seal(JOURNAL, name=rel)
anchors_path = REPO_ROOT / "blood" / "anchors.jsonl"
existing = [json.loads(l) for l in anchors_path.read_text(encoding="utf-8").splitlines() if l.strip()]
if not any(r.get("file") == rel and r.get("last_sha256") == anchor["last_sha256"] for r in existing):
    with anchors_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(anchor, ensure_ascii=False) + "\n")
    print("якорь опечатан")
else:
    print("якорь того же состояния уже в книге")

print("ИТОГ ВОЛНЫ №32:", json.dumps(results, ensure_ascii=False, indent=2))
