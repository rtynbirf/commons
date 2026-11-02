#!/usr/bin/env python3
"""Спайк S6: память — выбор векторного движка (ROADMAP M2, ADR-0007 (0.5.0)).

Базовая линия — stdlib sqlite3 (brute-force cosine KNN) — замеряется в CI.
Живые движки (chroma, lancedb, sqlite-vec) замеряются только при установке;
отсутствующий движок печатает NO_ENGINE (код 2) — цифры не выдумываются.

Запуск:
  python3 spikes/s6-memory/measure.py --matrix                 # офлайн: матрица кандидатов
  python3 spikes/s6-memory/measure.py --bench                  # базовая линия + попытка всех движков
  python3 spikes/s6-memory/measure.py --bench --engine chroma  # один движок (нет — NO_ENGINE, код 2)
Без флагов — как --bench.

Правила спайка (docs/spikes.md):
- одинаковые данные для всех: 200 векторов × dim 384, seed 42, нормализованные,
  cosine KNN top-10 для 20 запросов; вставка и запрос замеряются раздельно;
- замер — time.perf_counter; результат — markdown-строки для ADR-0007 (0.5.0);
- харнесс не выдумывает цифры: движок не установлен — NO_ENGINE (код 2), движок
  упал — фактический текст ошибки (код 2); без --engine отсутствующие помечаются
  «не установлен» в таблице (не ошибка, exit 0).

Зависимости: только стандартная библиотека Python 3.10+ (движки — опционально).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import random
import sqlite3
import tempfile
import time
from pathlib import Path

# Параметры замера — одинаковы для базовой линии и всех движков (честное сравнение).
N_VECTORS = 200
DIM = 384
N_QUERIES = 20
TOP_K = 10
SEED = 42
BENCH_SHAPE = f"{N_VECTORS}×{DIM}"

# Матрица кандидатов: лицензии и звёзды верифицированы живым GitHub API
# (GET /repos/{owner}/{repo}) 2026-11-02 — вставлены дословно; Graphify
# верифицирован 2026-11-01 (PROVENANCE.md §3). Спайк код движков не копирует.
CANDIDATE_MATRIX = (
    ("asg017/sqlite-vec · 8 232 ⭐", "Apache-2.0", "расширение sqlite",
     "в процессе", "кандидат: векторный движок M2"),
    ("chroma-core/chroma · 29 616 ⭐", "Apache-2.0", "встраиваемая библиотека (или сервер)",
     "в процессе (или отдельный сервис)", "кандидат: векторный движок M2"),
    ("lancedb/lancedb · 11 824 ⭐", "Apache-2.0", "встраиваемая columnar-БД",
     "в процессе", "кандидат: векторный движок M2"),
    ("qdrant/qdrant · 35 366 ⭐", "Apache-2.0", "серверный движок",
     "отдельный сервис", "кандидат: векторный движок M2"),
    ("Graphify-Labs/graphify", "Apache-2.0 (вериф. 2026-11-01)", "граф-слой знаний",
     "в процессе", "кандидат граф-слоя памяти — отдельное решение"),
    ("sqlite3 (stdlib)", "PSF (в составе CPython)", "brute-force cosine KNN",
     "в процессе", "базовая линия замера (идёт в CI)"),
)

# Движки бенча: имя → модуль для importlib.util.find_spec.
ENGINE_MODULES = {"chroma": "chromadb", "lancedb": "lancedb", "sqlite-vec": "sqlite_vec"}


def cosine(a: list[float], b: list[float]) -> float:
    """Косинусная близость, чистый Python без numpy: dot / (|a|·|b|); 0 для нулевых."""
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / math.sqrt(norm_a * norm_b)


def make_vectors(n: int, dim: int, seed: int = 42) -> list[list[float]]:
    """n нормализованных векторов размерности dim из random.Random(seed) — детерминированно.

    Одинаковый seed → одинаковые списки (проверяется тестами): базовая линия и
    движки меряются на одних и тех же данных.
    """
    rng = random.Random(seed)
    vectors: list[list[float]] = []
    for _ in range(n):
        vec = [rng.gauss(0.0, 1.0) for _ in range(dim)]
        norm = math.sqrt(math.fsum(x * x for x in vec))
        vectors.append([x / norm for x in vec])
    return vectors


def bench_sqlite3(
    n: int = N_VECTORS, dim: int = DIM, queries: int = N_QUERIES, top_k: int = TOP_K,
) -> tuple[float, float]:
    """Базовая линия stdlib: in-memory sqlite3 + brute-force cosine KNN top-10.

    Возвращает (insert_ms, query_ms). Вставка — executemany в in-memory базу.
    Запрос — полный перебор: строки один раз выгружаются в память (одноразовый
    «прогрев», аналог загрузки индекса движком), дальше замеряется чистый
    перебор — ровно то, что ANN-индекс живого движка должен сокращать.
    Работает всегда, в том числе в CI.
    """
    vectors = make_vectors(n, dim, seed=SEED)
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE vectors (id INTEGER PRIMARY KEY, vec TEXT NOT NULL)")
    started = time.perf_counter()
    connection.executemany(
        "INSERT INTO vectors (id, vec) VALUES (?, ?)",
        [(i, json.dumps(v)) for i, v in enumerate(vectors)],
    )
    connection.commit()
    insert_ms = (time.perf_counter() - started) * 1000.0

    stored = [json.loads(raw) for (raw,) in connection.execute("SELECT vec FROM vectors")]
    query_vectors = make_vectors(queries, dim, seed=SEED + 1)
    started = time.perf_counter()
    for q in query_vectors:
        scored = sorted(((cosine(q, v), i) for i, v in enumerate(stored)), reverse=True)
        _ = scored[:top_k]  # top-10 — форма результата, совпадает с движками
    query_ms = (time.perf_counter() - started) * 1000.0
    connection.close()
    return insert_ms, query_ms


def bench_chroma(
    tmp: Path, n: int = N_VECTORS, dim: int = DIM, queries: int = N_QUERIES, top_k: int = TOP_K,
) -> tuple[float, float]:
    """Честный мини-бенч chroma: PersistentClient во временный каталог; add → query."""
    import chromadb  # локальный импорт: движок может быть не установлен

    vectors = make_vectors(n, dim, seed=SEED)
    client = chromadb.PersistentClient(path=str(tmp / "chroma"))
    collection = client.get_or_create_collection("s6_bench")
    started = time.perf_counter()
    collection.add(ids=[str(i) for i in range(n)], embeddings=vectors)
    insert_ms = (time.perf_counter() - started) * 1000.0

    query_vectors = make_vectors(queries, dim, seed=SEED + 1)
    started = time.perf_counter()
    for q in query_vectors:
        collection.query(query_embeddings=[q], n_results=top_k)
    query_ms = (time.perf_counter() - started) * 1000.0
    return insert_ms, query_ms


def bench_lancedb(
    tmp: Path, n: int = N_VECTORS, dim: int = DIM, queries: int = N_QUERIES, top_k: int = TOP_K,
) -> tuple[float, float]:
    """Честный мини-бенч lancedb: create_table во временном каталоге; search → to_list.

    Урок волны-8 (2026-11-02): столбец из list[float] lancedb не считает векторным —
    нужна схема fixed_size_list (pyarrow — зависимость lancedb, не новый импорт),
    иначе ValueError «no vector column». Движок упал — факт; харнесс починен,
    цифры остаются цифрами замера.
    """
    import lancedb  # локальный импорт: движок может быть не установлен
    import pyarrow as pa  # зависимость lancedb (участвует в её публичном API)

    vectors = make_vectors(n, dim, seed=SEED)
    db = lancedb.connect(str(tmp / "lancedb"))
    flat = pa.array([x for v in vectors for x in v], type=pa.float32())
    vec_col = pa.FixedSizeListArray.from_arrays(flat, dim)
    data = pa.Table.from_arrays(
        [pa.array(range(n), type=pa.int64()), vec_col],
        schema=pa.schema([("id", pa.int64()), ("vec", pa.list_(pa.float32(), dim))]),
    )
    started = time.perf_counter()
    db.create_table("s6_bench", data=data)
    insert_ms = (time.perf_counter() - started) * 1000.0

    table = db.open_table("s6_bench")
    query_vectors = make_vectors(queries, dim, seed=SEED + 1)
    started = time.perf_counter()
    for q in query_vectors:
        table.search(q, vector_column_name="vec").limit(top_k).to_list()
    query_ms = (time.perf_counter() - started) * 1000.0
    return insert_ms, query_ms


def bench_sqlite_vec(
    tmp: Path, n: int = N_VECTORS, dim: int = DIM, queries: int = N_QUERIES, top_k: int = TOP_K,
) -> tuple[float, float]:
    """Честный мини-бенч sqlite-vec: загрузка расширения, виртуальная таблица vec0."""
    import sqlite_vec  # локальный импорт: движок может быть не установлен

    connection = sqlite3.connect(str(tmp / "s6-vec.db"))
    connection.enable_load_extension(True)
    sqlite_vec.load(connection)
    connection.enable_load_extension(False)
    connection.execute(f"CREATE VIRTUAL TABLE vectors USING vec0(embedding float[{dim}])")
    vectors = make_vectors(n, dim, seed=SEED)
    started = time.perf_counter()
    connection.executemany(
        "INSERT INTO vectors (rowid, embedding) VALUES (?, ?)",
        [(i, sqlite_vec.serialize_float32(v)) for i, v in enumerate(vectors)],
    )
    connection.commit()
    insert_ms = (time.perf_counter() - started) * 1000.0

    query_vectors = make_vectors(queries, dim, seed=SEED + 1)
    started = time.perf_counter()
    for q in query_vectors:
        connection.execute(
            "SELECT rowid, distance FROM vectors WHERE embedding MATCH ? AND k = ?"
            " ORDER BY distance",
            (sqlite_vec.serialize_float32(q), top_k),
        ).fetchall()
    query_ms = (time.perf_counter() - started) * 1000.0
    connection.close()
    return insert_ms, query_ms


ENGINE_BENCHES = {
    "chroma": bench_chroma,
    "lancedb": bench_lancedb,
    "sqlite-vec": bench_sqlite_vec,
}


def print_matrix() -> None:
    """Офлайн-матрица кандидатов: лицензии верифицированы, замеры — только --bench."""
    print("Матрица кандидатов спайка S6 — память: выбор векторного движка (ROADMAP M2, ADR-0007 (0.5.0)).")
    print("Лицензии и звёзды векторных кандидатов верифицированы живым GitHub API 2026-11-02;")
    print("Graphify — 2026-11-01 (PROVENANCE.md §3). Спайк код движков не копирует (ADR-0001).")
    print()
    print("| движок | лицензия (вериф. 2026-11-02) | режим | процесс | роль |")
    print("| --- | --- | --- | --- | --- |")
    for name, spdx, mode, process, role in CANDIDATE_MATRIX:
        print(f"| {name} | {spdx} | {mode} | {process} | {role} |")
    print()
    print("sqlite3 (stdlib) — не GitHub-кандидат: строка базовой линии для полноты матрицы.")
    print("Замеры: --bench (базовая линия sqlite3 всегда; живые движки — только установленные).")


def _bench_row(name: str, insert_ms: float, query_ms: float) -> str:
    """Одна строка бенча: движок | insert | query | объём."""
    return f"| {name} | insert {insert_ms:.1f} мс | query {query_ms:.1f} мс | {BENCH_SHAPE} |"


def _print_bench_table(rows: list[str]) -> None:
    print("Замер спайка S6 — cosine KNN top-10, одинаковые данные (200×384, seed 42):")
    print()
    print("| движок | вставка | запрос | объём |")
    print("| --- | --- | --- | --- |")
    for row in rows:
        print(row)
    print()
    print("Вердикт — в spikes/s6-memory/README.md; решение — ADR-0007 (0.5.0).")


def cmd_bench(engine: str | None) -> int:
    """Замер: базовая линия sqlite3 честная и всегда; движки — только установленные.

    engine=None — базовая линия + попытка всех трёх движков (отсутствующие —
    «не установлен» в таблице, exit 0); engine="sqlite3" — только базовая линия;
    engine из трёх живых — только этот движок: нет — NO_ENGINE (код 2), ошибка —
    фактический текст (код 2).
    """
    if engine is not None and engine != "sqlite3" and engine not in ENGINE_BENCHES:
        print(f"NO_ENGINE: движок '{engine}' не входит в спайк — доступны: sqlite3, "
              + ", ".join(sorted(ENGINE_BENCHES)) + ".")
        return 2

    rows: list[str] = []
    failed = False

    if engine is None or engine == "sqlite3":
        insert_ms, query_ms = bench_sqlite3()
        rows.append(_bench_row("sqlite3 (stdlib, brute-force)", insert_ms, query_ms))

    if engine is None:  # базовая линия уже напечатана; пробуем все три движка
        for name in sorted(ENGINE_BENCHES):
            if importlib.util.find_spec(ENGINE_MODULES[name]) is None:
                rows.append(f"| {name} | не установлен | — | {BENCH_SHAPE} |")
                continue
            try:
                with tempfile.TemporaryDirectory(prefix="s6-bench-") as tmp:
                    insert_ms, query_ms = ENGINE_BENCHES[name](Path(tmp))
                rows.append(_bench_row(name, insert_ms, query_ms))
            except Exception as error:  # движок есть, но замер не удался — печатаем факт
                rows.append(f"| {name} | ошибка: {type(error).__name__}: {error} | — | {BENCH_SHAPE} |")
                failed = True

    if engine in ENGINE_BENCHES:  # запрошен именно этот движок
        if importlib.util.find_spec(ENGINE_MODULES[engine]) is None:
            print(f"NO_ENGINE: {engine} не установлен — строка не замеряется, "
                  "спайк не врёт вместо замера.")
            return 2
        try:
            with tempfile.TemporaryDirectory(prefix="s6-bench-") as tmp:
                insert_ms, query_ms = ENGINE_BENCHES[engine](Path(tmp))
        except Exception as error:  # ошибка живого движка — как есть, без выдуманных чисел
            print(f"ENGINE_ERROR: {engine}: {type(error).__name__}: {error}")
            return 2
        rows.append(_bench_row(engine, insert_ms, query_ms))

    _print_bench_table(rows)
    if failed:
        print("NO_ENGINE: установленный движок не замерился (ошибка выше) — таблица неполна.")
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Спайк S6: память — выбор векторного движка")
    parser.add_argument("--matrix", action="store_true",
                        help="офлайн: матрица кандидатов (верифицированные лицензии)")
    parser.add_argument("--bench", action="store_true",
                        help="замер: базовая линия sqlite3 + живые движки (по умолчанию без флагов)")
    parser.add_argument("--engine", default=None,
                        help="sqlite3 | chroma | lancedb | sqlite-vec")
    args = parser.parse_args()
    if args.matrix:
        print_matrix()
        return 0
    return cmd_bench(args.engine)


if __name__ == "__main__":
    raise SystemExit(main())
