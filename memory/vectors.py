"""Векторный индекс памяти — базовая линия ADR-0007: stdlib sqlite3, brute-force cosine KNN.

Живой движок выбирается метриками спайка S6 (spikes/s6-memory) на живом хосте
организма; замена движка — правкой манифеста synapse/mcp-manifest.yaml, без
правки кода цикла (G2 SPEC-0005). Данные локальны: файл — только тот путь,
что дал конструктор (G3 SPEC-0005).

Права забывания и выгрузки (SPEC-0005 пп.7–8, волна №27): delete/delete_by_trace/
get/items — дополнения реализации (как close()): протокол VectorIndex цикла
их не знает (G2), движок без них честно отчитается OUT_OF_CONTROL в memory.forget.
Трейс забывается вместе с подтрейсами `<trace_id>-*` (та же конвенция дома,
что и в графе: сцены и стыки называются `<трейс>-<имя>`).
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


def _trace_matches(actual: Any, wanted: str) -> bool:
    """Конвенция подтрейсов дома: точный трейс или `<trace_id>-*` (SPEC-0005 п.7).

    Одна и та же в индексе (delete_by_trace) и в графе (forget_trace) —
    иначе забывание двух хранилищ разъедется.
    """
    if actual is None:
        return False
    actual = str(actual)
    return actual == wanted or actual.startswith(wanted + "-")


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

    def ids(self) -> list[str]:
        """Все vec_id индекса (ТЗ-1.1, A11/A13: экспорт и diff память-файлов)."""
        return [row[0] for row in self._connection.execute("SELECT vec_id FROM vectors ORDER BY vec_id")]

    def forget(self, vec_id: str) -> bool:
        """Забывает запись (ТЗ-1.1, A12): True — была и удалена, False — её не было.

        Удаление из производной честно: сама запись не возвращается; кровь
        (истина) этим методом не трогается — забвение крови не существует.
        """
        cursor = self._connection.execute("DELETE FROM vectors WHERE vec_id = ?", (vec_id,))
        return cursor.rowcount > 0

    def count(self) -> int:
        """Число векторов в индексе."""
        (total,) = self._connection.execute("SELECT COUNT(*) FROM vectors").fetchone()
        return int(total)

    def get(self, vec_id: str) -> tuple[list[float], dict[str, Any]] | None:
        """Вектор с метаданными по id — или None (для сверки при импорте, п.8)."""
        row = self._connection.execute(
            "SELECT vec, meta FROM vectors WHERE vec_id = ?", (vec_id,)
        ).fetchone()
        if row is None:
            return None
        return json.loads(row[0]), json.loads(row[1])

    def items(self) -> list[tuple[str, list[float], dict[str, Any]]]:
        """Все записи (vec_id, vector, meta) — материал экспорта снапшота (п.8)."""
        return [
            (vec_id, json.loads(raw_vec), json.loads(raw_meta))
            for vec_id, raw_vec, raw_meta in self._connection.execute(
                "SELECT vec_id, vec, meta FROM vectors ORDER BY vec_id"
            )
        ]

    def delete(self, vec_id: str) -> bool:
        """Забывает одну запись; True — была и удалена, False — не было (п.7).

        Как и add, живёт в транзакции: фактическая запись файла — flush().
        """
        cursor = self._connection.execute("DELETE FROM vectors WHERE vec_id = ?", (vec_id,))
        return cursor.rowcount > 0

    def delete_by_trace(self, trace_id: str) -> int:
        """Забывает все записи трейса и его подтрейсов `<trace_id>-*`; возвращает число.

        Совпадение — по meta.trace_id: точное или подтрейс (конвенция дома).
        Как и add, живёт в транзакции: фактическая запись файла — flush().
        """
        wanted = str(trace_id)
        doomed = [
            vec_id
            for vec_id, raw_meta in self._connection.execute("SELECT vec_id, meta FROM vectors")
            if _trace_matches(json.loads(raw_meta).get("trace_id"), wanted)
        ]
        for vec_id in doomed:
            self._connection.execute("DELETE FROM vectors WHERE vec_id = ?", (vec_id,))
        return len(doomed)

    def flush(self) -> None:
        """COMMIT — фактическая запись файла (путь только из конструктора, G3)."""
        self._connection.commit()

    def close(self) -> None:
        """Закрывает соединение (не в протоколе — дополнение реализации)."""
        self._connection.close()
