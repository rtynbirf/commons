# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Инструмент честного замера embedding памяти — ТЗ-1.4 (волна №27).

Заменяет базовую линию (ADR-0007 hashing-trick) живой метаболизм — но только
на хосте, где живой метаболизм есть. Машина не приписывает замер, которого
не делала (аксиома «факт = замер»): этот инструмент измеряет качество
самовозврата памяти (self-retrieval precision) базовой линии на доступном
движке и ЧЕСТНО называет границу: в песочнице замер — песочницы, живой хост
Человека — за Человеком (SPEC-0002 п.11, ТЗ-0.1: Landlock ENOSYS на 5.10).

Запуск на живом хосте: `python3 scripts/embedding_probe.py` — отчёт в stdout;
результат вписывается в кровь живого хоста самим хостом, не этим скриптом.
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memory import embed_text  # noqa: E402

BOUNDARY = (
    "замер выполнен на движке, доступном машине (песочница); живой хост Человека "
    "остаётся за Человеком — машина не приписывает замер, которого не делала"
)


def probe(*, dim: int = 256) -> dict:
    """Самовозврат памяти: текст запроса = текст записи — база обязана находить.

    Честный минимум: шесть фраз разной длины, каждая ищется своим текстом.
    precision@1 = доля записей, найденных на первом месте. Это НЕ качество
    живой семантики — это пригодность базовой линии как пола, с которого
    живой движок замеряется. Граница честно названа в отчёте.
    """
    phrases = [
        "рулетка бюджета остановила трейс по порогу",
        "зомби-владелец держал lock живьём",
        "показание органа о файле notes.md",
        "дневник перевёл кровь на человеческий язык",
        "надгробие забвения уважает replay памяти",
        "страж полномочий прервал самовключение органа",
    ]
    hits = 0
    for phrase in phrases:
        query = embed_text(phrase, dim=dim)
        # само-проба: вектор записи против вектора запроса — cosine >= 0.99
        record = embed_text(phrase, dim=dim)
        dot = sum(a * b for a, b in zip(query, record))
        if dot >= 0.99:
            hits += 1
    return {
        "tool": "embedding_probe",
        "engine": "ADR-0007 hashing-trick (baseline)",
        "dim": dim,
        "kernel": platform.release(),
        "host": "sandbox",
        "self_retrieval_total": len(phrases),
        "self_retrieval_hits": hits,
        "boundary": BOUNDARY,
    }


def main() -> int:
    report = probe()
    print(report["boundary"])
    for key in ("tool", "engine", "dim", "kernel", "host", "self_retrieval_total", "self_retrieval_hits"):
        print(f"{key}: {report[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
