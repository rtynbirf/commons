"""Контракт памяти (SPEC-0005) — исполняемые интерфейсы и общая база.

Домашний метод «спека раньше кода»: этот модуль — контракт, реализации следуют за ним:
- `memory.vectors.SQLiteVectorIndex` — векторный индекс (базовая линия ADR-0007);
- `memory.graph.MemoryGraph` — граф знаний;
- `memory.engine.MemoryFacade` — фасад памяти для ствола мозга;
- `memory.replay.replay` — восстановление памяти из крови (G1).

Память — кэш-советник: кровь (SPEC-0003) — истина. Индексация — только после
REFLECT (SPEC-0005 п.1); чтение PLAN-ом — read-only (п.5); данные локальны
по умолчанию (G3); смена движка — без правки цикла (G2).
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class VectorIndex(Protocol):
    """Векторный индекс. G2: реализаций может быть много — цикл не знает ни одной."""

    def add(self, vec_id: str, vector: list[float], meta: dict[str, Any]) -> None:
        """Запоминает вектор с метаданными (повторный id — замена записи)."""
        ...

    def search(self, vector: list[float], k: int = 5) -> list[tuple[str, float, dict[str, Any]]]:
        """k ближайших: (vec_id, сходство, meta), по убыванию сходства."""
        ...

    def count(self) -> int:
        """Число векторов в индексе."""
        ...

    def flush(self) -> None:
        """Сохраняет состояние на диск (для персистентных движков)."""
        ...


@runtime_checkable
class MemoryGraph(Protocol):
    """Граф знаний: узлы source/organ/tool, рёбра — обмены с trace_id."""

    def add_envelope(self, envelope: dict[str, Any]) -> None:
        """Вплетает конверт крови в граф; повтор конверта (по id) не меняет граф."""
        ...

    def neighbors(self, node: str, k: int = 5) -> list[dict[str, Any]]:
        """До k соседей узла: [{node, weight, via}] — по убыванию веса."""
        ...

    def stats(self) -> dict[str, int]:
        """Анатомия графа: {nodes, edges}."""
        ...

    def flush(self) -> None:
        """Сохраняет состояние на диск (для персистентных движков)."""
        ...


@runtime_checkable
class Memory(Protocol):
    """Фасад памяти для ствола мозга (SPEC-0005 п.1 и п.5)."""

    def observe(self, envelope: dict[str, Any]) -> None:
        """Индексация одного конверта после REFLECT (граф + вектора)."""
        ...

    def context(self, intent: str, k: int = 3) -> list[dict[str, Any]]:
        """Read-only контекст для PLAN: релевантные воспоминания."""
        ...


def embed_text(text: str, dim: int = 256) -> list[float]:
    """Базовая линия векторизации (ADR-0007): детерминированный hashing trick.

    Токены текста хешируются в dim корзин (bag-of-words со знаком), вектор
    нормализуется. Это честная «семантика» уровня совпадения слов — до живого
    embedding от метаболизма; замена — правкой манифеста, без кода цикла (G2).
    """
    buckets = [0.0] * dim
    for token in str(text).lower().split():
        digest = hashlib.sha1(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        buckets[idx] += sign
    norm = math.sqrt(sum(b * b for b in buckets)) or 1.0
    return [b / norm for b in buckets]
