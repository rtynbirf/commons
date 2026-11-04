# -*- coding: utf-8 -*-
"""taskgraph — единый пропагатор планов организма (SPEC-0011, ADR-0018).

Один алгоритм `sweep` в полукольце S даёт все функции структуры графа задач:
достижимость, расписание и критический путь, резервы, кратчайший маршрут,
статсумму путей, надёжность, узкое место, производящую функцию, фронт
Парето «время × надёжность», свободную энергию и крэшинг-контур.

Граф с циклами — `pathsum`; все пары — `closure`; инкрементальный жанр
(ячейки и покой, Radul/Sussman) — `propagate_network`; матричный жанр
(GraphBLAS) — `sweep_matrix`.

Тест отключения (G2): ядро дома этот пакет не импортирует — выдёргивается
без правок других слоёв; приёмка это держит (tests/test_taskgraph.py).
"""
from __future__ import annotations

from .graph import TaskGraph, kahn
from .sweep import (Cell, closure, pathsum, propagate_network, sweep,
                    sweep_matrix, worldline)
from .schedule import (compact_report, crash_contour, criticality,
                       early, free_energy, late, makespan)
from .semiring import (BOOL, BOTT, COUNT, MAXP, MINP, PARETO, POLY, VITER,
                       Semiring, by_name, logsum_semiring)

__version__ = "0.51.0"

__all__ = [
    "TaskGraph", "kahn",
    "sweep", "sweep_matrix", "closure", "pathsum", "propagate_network",
    "Cell", "worldline",
    "early", "late", "makespan", "criticality", "free_energy",
    "crash_contour", "compact_report",
    "BOOL", "MAXP", "MINP", "COUNT", "VITER", "BOTT", "POLY", "PARETO",
    "Semiring", "logsum_semiring", "by_name",
]
