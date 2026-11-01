"""Векторный индекс памяти — базовая линия ADR-0007: stdlib sqlite3, brute-force cosine KNN.

Живой движок выбирается метриками спайка S6 (spikes/s6-memory) на живом хосте
организма; замена движка — правкой манифеста synapse/mcp-manifest.yaml, без
правки кода цикла (G2 SPEC-0005). Данные локальны: файл — только тот путь,
что дал конструктор (G3 SPEC-0005).
"""

from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS vectors (
    vec_id TEXT PRIMARY KEY,
    vec TEXT NOT NULL,
    meta TEXT NOT NULL
)
"""


def cosine(a: list[float], b: list[float]) -> float:
    """Косинусная близость: dot / (|a|·|b|); нулевой вектор даёт 0.0.

    Локальная функция в стиле базовой линии спайка S6 (чистый Python, без
    numpy): спайк код движков не копирует, и память не импортирует спайк.
    """
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


class SQLiteVectorIndex:
    """Векторный индекс на stdlib sqlite3 — базовая линия ADR-0007.

    Brute-force cosine KNN: каждый запрос перебирает все строки таблицы
    vectors — ровно то, что живой движок (по метрикам спайка S6) должен
    сокращать. Реализует протокол VectorIndex из memory/__init__.py: цикл
    знает только протокол, а не эту реализацию (G2).

    Персистентность: add копит записи в транзакции, flush() делает COMMIT —
    фактическую запись файла; до flush() файл на диске данных не содержит
    (память — кэш, кровь — истина, восстановление replay-ем — G1 SPEC-0005).
    Файл базы создаётся при инициализации по пути из конструктора.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._connection = sqlite3.connect(str(self._path))
        self._connection.execute(_CREATE_TABLE)
        self._connection.commit()

    def add(self, vec_id: str, vector: list[float], meta: dict[str, Any]) -> None:
        """Запоминает вектор с метаданными (повторный id — замена записи)."""
        self._connection.execute(
            "INSERT OR REPLACE INTO vectors (vec_id, vec, meta) VALUES (?, ?, ?)",
            (
                vec_id,
                json.dumps([float(x) for x in vector]),
                json.dumps(meta, ensure_ascii=False),
            ),
        )

    def search(self, vector: list[float], k: int = 5) -> list[tuple[str, float, dict[str, Any]]]:
        """k ближайших: (vec_id, сходство, meta), по убыванию сходства.

        Полный перебор строк с локальной cosine; при равенстве сходства —
        стабильный порядок по vec_id. Пустой индекс — пустой список.
        """
        query = [float(x) for x in vector]
        scored: list[tuple[str, float, dict[str, Any]]] = []
        for vec_id, raw_vec, raw_meta in self._connection.execute(
            "SELECT vec_id, vec, meta FROM vectors"
        ):
            scored.append((vec_id, cosine(query, json.loads(raw_vec)), json.loads(raw_meta)))
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:k] if k > 0 else []

    def count(self) -> int:
        """Число векторов в индексе."""
        (total,) = self._connection.execute("SELECT COUNT(*) FROM vectors").fetchone()
        return int(total)

    def flush(self) -> None:
        """COMMIT — фактическая запись файла (путь только из конструктора, G3)."""
        self._connection.commit()

    def close(self) -> None:
        """Закрывает соединение (не в протоколе — дополнение реализации)."""
        self._connection.close()
