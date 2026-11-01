"""Фасад памяти и сборка движка из манифеста — SPEC-0005 п.1, п.2 и G2.

MemoryFacade — ровно протокол Memory (observe + context) из memory/__init__.py:
- observe() — индексация конверта ПОСЛЕ REFLECT (SPEC-0005 п.1): индексация
  никогда не замедляет и не ломает действие;
- context() — read-only чтение для PLAN (SPEC-0005 п.5): память — советник,
  не приказчик, писать при чтении нечего.

flush() движков при observe не вызывается: сохранение состояния — дело того,
кто завершает сессию (facade.index.flush() / facade.graph.flush() либо replay).

DefaultMemory — удобный конкретный фасад (базовая линия ADR-0007). Реализации
memory.vectors / memory.graph собираются отдельной волной, поэтому импорт
ленивый — внутри __init__, с честной ошибкой, если файла ещё нет.

memory_from_manifest — G2 SPEC-0005 п.2: движок памяти объявлен в манифесте
как орган (system: memory); замена движка — правка манифеста, без правки кода
ствола мозга. Нет объявления или движок не развёрнут (SPEC-0002 п.6) — None:
цикл живёт без памяти (degrade SPEC-0005). Кроме PyYAML для манифеста
(так же читает шлюз — уже зависимость тела) — только stdlib.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any

import yaml

from memory import Memory, embed_text
from memory.replay import envelope_meta, envelope_text

# Базовая линия векторизации (ADR-0007): dim контракта embed_text.
_DIM = 256

# Система органа-движка памяти в манифесте (SPEC-0005 п.2).
MEMORY_SYSTEM = "memory"


class MemoryFacade:
    """Фасад памяти для ствола мозга: ровно протокол Memory, никаких других методов.

    Движки (index, graph) передаются снаружи — фасад ничего не знает о их
    реализации (G2): циклу достаточно протокола Memory.
    """

    def __init__(self, index: Any, graph: Any) -> None:
        self.index = index
        self.graph = graph

    def observe(self, envelope: dict[str, Any]) -> None:
        """Индексация одного конверта после REFLECT: граф + вектор.

        Текст и meta — те же, что в replay (memory.replay): иначе пустой
        движок, заполненный replay-ем, перестал бы быть эквивалентен живой
        памяти (G1 SPEC-0005). flush() здесь не вызывается — его делает тот,
        кто завершает сессию.
        """
        self.graph.add_envelope(envelope)
        self.index.add(envelope["id"], embed_text(envelope_text(envelope), dim=_DIM), envelope_meta(envelope))

    def context(self, intent: str, k: int = 3) -> list[dict[str, Any]]:
        """Read-only контекст для PLAN: релевантные воспоминания.

        Возвращает [{"id", "score", "meta"}] по убыванию сходства. Ничего не
        пишет ни в индекс, ни в граф — у памяти нет эффекторных прав (SPEC-0005 п.5).
        """
        hits = self.index.search(embed_text(intent, dim=_DIM), k)
        return [{"id": vec_id, "score": score, "meta": meta} for vec_id, score, meta in hits]


class DefaultMemory(MemoryFacade):
    """Конкретный фасад по умолчанию: SQLiteVectorIndex + MemoryGraph (ADR-0007).

    Реализации подключаются ленивым импортом внутри __init__ — файлы
    memory/vectors.py и memory/graph.py собираются отдельной волной; если их
    ещё нет, ошибка честно говорит об этом, а не падает traceback-ом импорта.
    """

    def __init__(self, workdir: Path) -> None:
        try:
            from memory.vectors import SQLiteVectorIndex
            from memory.graph import MemoryGraph
        except ImportError as exc:
            raise RuntimeError(f"реализация хранилища ещё не собрана: {exc}") from exc
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)  # тело готовит место; файлы — движков
        super().__init__(SQLiteVectorIndex(workdir / "vectors.sqlite"), MemoryGraph(workdir / "graph.jsonl"))


def _memory_organ(manifest_path: Path) -> dict[str, Any] | None:
    """Находит в манифесте первую запись органа с system == memory (SPEC-0005 п.2)."""
    raw = yaml.safe_load(Path(manifest_path).read_text(encoding="utf-8"))
    organs = raw.get("organs") if isinstance(raw, dict) else None
    for entry in organs or []:
        if isinstance(entry, dict) and entry.get("system") == MEMORY_SYSTEM:
            return entry
    return None


def _takes_workdir(cls: type) -> bool:
    """Есть ли у класса адаптера параметр workdir в __init__."""
    try:
        parameters = inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):  # не интроспектируемое __init__ — зовём без аргументов
        return False
    return "workdir" in parameters


def _load_adapter(dotted: str) -> type:
    """Динамическая загрузка класса адаптера «module:Class» — стиль загрузчика шлюза."""
    try:
        module_path, class_name = dotted.split(":")
        return getattr(importlib.import_module(module_path), class_name)
    except Exception as exc:  # noqa: BLE001 — ошибка конфигурации всегда видна честно
        raise ValueError(f"адаптер памяти {dotted!r} не загрузился: {exc}") from exc


def memory_from_manifest(manifest_path: Path, workdir: Path) -> Memory | None:
    """Собирает движок памяти из манифеста (G2 SPEC-0005 п.2) — или None.

    - органа с system: memory нет → None: память не объявлена — цикл живёт без неё;
    - орган есть, но command отсутствует или "none" → None: движок не развёрнут,
      degrade честно по SPEC-0002 п.6;
    - орган есть с adapter («module:Class») → динамический импорт (зеркало
      загрузчика шлюза), инстанцирование с workdir, если класс его принимает;
      результат обязан удовлетворять протоколу Memory — иначе ValueError.

    Поднятый ValueError — конфигурационная ошибка манифеста: объявленный, но
    сломанный движок памяти не молчит (в отличие от необъявленного).
    """
    entry = _memory_organ(manifest_path)
    if entry is None:
        return None

    command = entry.get("command")
    if command is None or command == "none":
        return None  # SPEC-0002 п.6: адрес/команда не развёрнуты — движка нет

    dotted = entry.get("adapter")
    if not dotted:
        return None  # адаптер не назначен — собирать нечего

    cls = _load_adapter(str(dotted))
    engine = cls(workdir=workdir) if _takes_workdir(cls) else cls()

    if not isinstance(engine, Memory):
        raise ValueError(
            f"адаптер памяти {dotted!r} не реализует протокол Memory "
            "(нужны методы observe(envelope) и context(intent, k=3))"
        )
    return engine
