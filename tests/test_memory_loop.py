"""Приёмка SPEC-0005 в стволе мозга: память в цикле — на своих фейках.

Тесты опираются ТОЛЬКО на контракт memory/__init__.py (протоколы
VectorIndex/MemoryGraph/Memory + embed_text) и фейки этого файла. Реальные
реализации memory.vectors / memory.graph здесь не импортируются — их собирает
параллельная волна; DefaultMemory проверяется только на ленивый импорт.

Проверяется: индексация после REFLECT (п.1), read-only чтение PLAN-ом (п.5),
G1 «кровь — истина» (replay), G2 «смена движка — правкой манифеста»,
отказной режим (degrade) и G3 «replay не создаёт файлов сам».
"""

from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from blood.envelope import make
from blood.journal import Journal
from brainstem import Loop
from memory import Memory, VectorIndex, MemoryGraph
from memory.engine import DefaultMemory, MemoryFacade, memory_from_manifest
from memory.replay import replay

from .conftest import MANIFEST, step  # noqa: TID252


# --- фейки памяти (свои подставки; реальные движки — параллельная волна) ------


class FakeMemory:
    """Фейковый Memory: счётчики observe/context + готовый ответ context."""

    def __init__(self, context_reply: list[dict[str, Any]] | None = None) -> None:
        self.observed: list[dict[str, Any]] = []
        self.context_calls: list[str] = []
        self.context_reply = list(context_reply or [])
        self.observed_at: list[bool] = []  # был ли reflect уже в крови в момент observe
        self.observed_at_context: list[int] = []  # счётчик observe в момент context
        self._journal: Journal | None = None

    def watch_journal(self, journal: Journal) -> None:
        self._journal = journal

    def observe(self, envelope: dict[str, Any]) -> None:
        if self._journal is not None:
            self.observed_at.append(any(e["type"] == "reflect" for e in self._journal.all()))
        self.observed.append(envelope)

    def context(self, intent: str, k: int = 3) -> list[dict[str, Any]]:
        self.observed_at_context.append(len(self.observed))
        self.context_calls.append(intent)
        return list(self.context_reply)


class BrokenMemory:
    """Память, которая падает на любом касании (отказной режим SPEC-0005)."""

    def observe(self, envelope: dict[str, Any]) -> None:
        raise RuntimeError("память сломалась на observe")

    def context(self, intent: str, k: int = 3) -> list[dict[str, Any]]:
        raise RuntimeError("память сломалась на context")


class FakeMemoryA:
    """Адаптер памяти A для G2: устанавливается из манифеста динамически."""

    def __init__(self, workdir: Path | None = None) -> None:
        self.workdir = workdir
        self.observed: list[dict[str, Any]] = []
        self.context_calls: list[str] = []

    def observe(self, envelope: dict[str, Any]) -> None:
        self.observed.append(envelope)

    def context(self, intent: str, k: int = 3) -> list[dict[str, Any]]:
        self.context_calls.append(intent)
        return []


class FakeMemoryB(FakeMemoryA):
    """Адаптер памяти B для G2: другой класс, тот же протокол."""


class FakeMemoryBare:
    """Адаптер без параметра workdir: инстанцируется без аргументов."""

    def __init__(self) -> None:
        self.workdir = None
        self.observed: list[dict[str, Any]] = []

    def observe(self, envelope: dict[str, Any]) -> None:
        self.observed.append(envelope)

    def context(self, intent: str, k: int = 3) -> list[dict[str, Any]]:
        return []


class NotMemory:
    """Не память: нет observe/context — протокол Memory нарушен."""

    def __init__(self, workdir: Path | None = None) -> None:
        self.workdir = workdir


# --- stub-движки контракта (для replay: G1/G3 и фасада) -----------------------


class StubVectorIndex:
    """Stub VectorIndex: всё в памяти; поиск — brute-force косинус."""

    def __init__(self) -> None:
        self.vectors: dict[str, tuple[list[float], dict[str, Any]]] = {}
        self.flushes = 0

    def add(self, vec_id: str, vector: list[float], meta: dict[str, Any]) -> None:
        self.vectors[vec_id] = (list(vector), dict(meta))

    def search(self, vector: list[float], k: int = 5) -> list[tuple[str, float, dict[str, Any]]]:
        def cosine(a: list[float], b: list[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a)) or 1.0
            nb = math.sqrt(sum(y * y for y in b)) or 1.0
            return dot / (na * nb)

        ranked = sorted(
            ((vid, cosine(vector, vec), meta) for vid, (vec, meta) in self.vectors.items()),
            key=lambda item: item[1],
            reverse=True,
        )
        return ranked[:k]

    def count(self) -> int:
        return len(self.vectors)

    def flush(self) -> None:
        self.flushes += 1


class StubMemoryGraph:
    """Stub MemoryGraph: узлы — source/organ/tool, рёбра — обмены с trace_id."""

    def __init__(self) -> None:
        self.nodes: set[str] = set()
        self.edges: set[tuple[str, str, str, str]] = set()
        self.flushes = 0

    def add_envelope(self, envelope: dict[str, Any]) -> None:
        tool = envelope.get("payload", {}).get("tool")
        tool = tool if isinstance(tool, str) else ""
        self.nodes.update((envelope["source"], envelope["organ"]))
        if tool:
            self.nodes.add(tool)
        self.edges.add((envelope["trace_id"], envelope["source"], envelope["organ"], tool))

    def neighbors(self, node: str, k: int = 5) -> list[dict[str, Any]]:
        return []

    def stats(self) -> dict[str, int]:
        return {"nodes": len(self.nodes), "edges": len(self.edges)}

    def flush(self) -> None:
        self.flushes += 1


def expected_anatomy(events: list[dict[str, Any]]) -> tuple[set[str], set[tuple[str, str, str, str]]]:
    """Ручной пересчёт анатомии графа из журнала — оракул для stub-графа (G1)."""
    nodes: set[str] = set()
    edges: set[tuple[str, str, str, str]] = set()
    for envelope in events:
        tool = envelope["payload"].get("tool")
        tool = tool if isinstance(tool, str) else ""
        nodes.update((envelope["source"], envelope["organ"]))
        if tool:
            nodes.add(tool)
        edges.add((envelope["trace_id"], envelope["source"], envelope["organ"], tool))
    return nodes, edges


def manifest_with_memory(adapter: str, command: Any = "memory-engine") -> dict[str, Any]:
    """Манифест формы conftest + орган-движок памяти (SPEC-0005 п.2)."""
    manifest = copy.deepcopy(MANIFEST)
    organ: dict[str, Any] = {
        "name": "memory-core",
        "system": "memory",
        "mode": "dependency",
        "upstream": "https://example.invalid/memory",
        "license": "MIT",
        "transport": "stdio",
        "healthcheck": "initialize handshake",
        "tools": ["remember", "recall"],
        "authority": {"fs": "read-write-workdir", "network": "none"},
    }
    if command is not None:
        organ["command"] = command
    if adapter:
        organ["adapter"] = adapter
    manifest["organs"].append(organ)
    return manifest


def write_manifest(tmp_path: Path, name: str, manifest: dict[str, Any]) -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    return path


# --- индексация после REFLECT (SPEC-0005 п.1) ---------------------------------


def test_observe_called_once_after_reflect(manifest_path, journal, gateway) -> None:
    memory = FakeMemory()
    memory.watch_journal(journal)
    loop = Loop(gateway, journal, memory=memory)

    assert loop.run([step(intent="запомни меня")]) is True
    assert len(memory.observed) == 1
    # Порядок: в момент observe reflect-конверт уже в крови (индексация после REFLECT).
    assert memory.observed_at == [True]
    # И это именно тот reflect-конверт, что записан в кровь (по id).
    (reflect,) = journal.by_type("reflect")
    assert memory.observed[0]["type"] == "reflect"
    assert memory.observed[0]["id"] == reflect["id"]
    assert memory.observed[0]["payload"]["satisfied"] is True


def test_observe_runs_on_every_reflect_including_halt_paths(manifest_path, journal, gateway) -> None:
    """REFLECT при veto тоже попадает в память: конверт уже в крови (SPEC-0005 п.1)."""
    memory = FakeMemory()
    memory.watch_journal(journal)
    loop = Loop(gateway, journal, memory=memory)

    assert loop.run([step(tool="запрещённый-инструмент")]) is False
    (reflect,) = journal.by_type("reflect")
    assert len(memory.observed) == 1
    assert memory.observed_at == [True]
    assert memory.observed[0]["id"] == reflect["id"]
    assert memory.observed[0]["payload"]["satisfied"] is False


# --- PLAN читает память read-only (SPEC-0005 п.5) -----------------------------


def test_plan_reads_memory_readonly(manifest_path, journal, gateway) -> None:
    reply = [{"id": "mem-1", "score": 0.9, "meta": {"type": "reflect", "trace_id": "old"}}]
    memory = FakeMemory(context_reply=reply)
    loop = Loop(gateway, journal, memory=memory)

    assert loop.run([step(intent="узнай про эхо")]) is True

    # context вызван с intent шага; observe во время PLAN ещё не звался.
    assert memory.context_calls == ["узнай про эхо"]
    assert memory.observed_at_context == [0]
    # Контекст попал в plan-событие крови как memory_context.
    (plan,) = journal.by_type("plan")
    assert plan["payload"]["memory_context"] == reply
    # Read-only: в крови — копия; мутация ответа памяти не меняет записанное.
    reply[0]["score"] = 0.0
    reply[0]["meta"]["type"] = "MUTATED"
    assert plan["payload"]["memory_context"][0]["score"] == 0.9
    assert plan["payload"]["memory_context"][0]["meta"]["type"] == "reflect"


def test_empty_context_not_written_to_plan(manifest_path, journal, gateway) -> None:
    loop = Loop(gateway, journal, memory=FakeMemory())  # context_reply пуст
    assert loop.run([step()]) is True
    (plan,) = journal.by_type("plan")
    assert "memory_context" not in plan["payload"]


def test_memory_none_keeps_loop_as_before(manifest_path, journal, gateway) -> None:
    loop = Loop(gateway, journal)
    assert loop.run([step(intent="как раньше")]) is True
    assert [e["type"] for e in journal.by_trace(journal.all()[0]["trace_id"])] == [
        "plan",
        "act",
        "observe",
        "reflect",
    ]
    assert not journal.by_type("error")


# --- G1: кровь — истина (replay пустым движком) --------------------------------


def test_replay_blood_is_truth(manifest_path, journal, gateway, tmp_path) -> None:
    memory = FakeMemory()
    loop = Loop(gateway, journal, memory=memory)
    assert loop.run([step(intent="шаг раз"), step(intent="шаг два")], trace_id="g1-truth") is True

    blood = tmp_path / "blood.jsonl"
    journal.to_jsonl(blood)

    index, graph = StubVectorIndex(), StubMemoryGraph()
    assert isinstance(index, VectorIndex) and isinstance(graph, MemoryGraph)

    report = replay(blood, index=index, graph=graph)

    events = list(journal.by_trace("g1-truth"))
    reflects = [e for e in events if e["type"] == "reflect"]
    assert report["envelopes"] == len(events)
    # SPEC-0005 п.1: память хранит то, что прошло REFLECT; replay обязан
    # индексировать ровно то же, иначе G1-эквивалентность живой памяти нарушена.
    assert report["indexed"] == len(reflects)
    assert report["skipped"] == 0

    # Анатомия графа — ручной пересчёт reflect-обменов сессии (source/organ/tool).
    nodes, edges = expected_anatomy(reflects)
    assert report["graph"]["nodes"] == len(nodes)
    assert report["graph"]["edges"] == len(edges)

    # Вектора — базовая линия контракта: dim=256, meta честный.
    assert all(len(vector) == 256 for vector, _ in index.vectors.values())
    reflect = reflects[0]
    assert index.vectors[reflect["id"]][1] == {"type": "reflect", "source": "brainstem", "trace_id": "g1-truth"}

    # Сессия завершена — replay сохранил оба движка.
    assert index.flushes == 1
    assert graph.flushes == 1


def test_replay_counts_skipped_honestly(tmp_path) -> None:
    good = [
        make("reflect", "brainstem", "self", "re-1", {"intent": "выучить", "satisfied": True}),
        make("plan", "brainstem", "sense-a", "re-1", {"index": 0, "tool": "echo", "intent": "выучить"}),
    ]
    lines = [
        json.dumps(good[0], ensure_ascii=False),
        "{битая строка без json",
        "42",  # json, но не dict
        json.dumps({"no": "required fields"}),  # dict без обязательных полей конверта
        json.dumps(good[1], ensure_ascii=False),
        "",  # пустая строка
    ]
    blood = tmp_path / "blood.jsonl"
    blood.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = replay(blood, index=StubVectorIndex(), graph=StubMemoryGraph())

    assert report["envelopes"] == 2
    # В память входит только reflect (SPEC-0005 п.1); plan — в крови, не в памяти.
    assert report["indexed"] == 1
    assert report["skipped"] == 4


def test_envelope_text_collects_string_leaves_recursively() -> None:
    from memory.replay import envelope_text

    envelope = {
        "id": "x",
        "type": "observe",
        "source": "brainstem",
        "organ": "sense-a",
        "trace_id": "t",
        "payload": {"tool": "echo", "result": {"echo": {"data": "глубокий лист"}, "n": 7}, "tags": ["а", "б"]},
    }
    text = envelope_text(envelope)
    assert text == "observe brainstem sense-a echo глубокий лист а б"


# --- MemoryFacade: тот же текст/meta, что replay; context — read-only ----------


def test_facade_indexing_matches_replay(tmp_path) -> None:
    envelope = make("reflect", "brainstem", "self", "facade-1", {"intent": "выучить эхо", "satisfied": True})

    facade = MemoryFacade(StubVectorIndex(), StubMemoryGraph())
    assert isinstance(facade, Memory)
    facade.observe(envelope)

    # Тот же конверт через replay — тот же вектор и та же meta (G1-эквивалентность).
    blood = tmp_path / "one.jsonl"
    blood.write_text(json.dumps(envelope, ensure_ascii=False) + "\n", encoding="utf-8")
    replay_index, replay_graph = StubVectorIndex(), StubMemoryGraph()
    report = replay(blood, index=replay_index, graph=replay_graph)

    assert report["envelopes"] == 1 and report["indexed"] == 1
    assert facade.index.vectors[envelope["id"]] == replay_index.vectors[envelope["id"]]


def test_facade_context_maps_search_and_writes_nothing() -> None:
    facade = MemoryFacade(StubVectorIndex(), StubMemoryGraph())
    env_a = make("reflect", "brainstem", "self", "t-a", {"intent": "эхо органов"})
    env_b = make("reflect", "brainstem", "self", "t-b", {"intent": "браузер и клики"})
    facade.observe(env_a)
    facade.observe(env_b)

    before_index, before_graph = facade.index.count(), facade.graph.stats()
    hits = facade.context("эхо органов", k=2)

    assert hits and all(set(item) == {"id", "score", "meta"} for item in hits)
    assert hits[0]["id"] == env_a["id"]  # релевантное — выше нерелевантного
    assert hits[0]["meta"] == {"type": "reflect", "source": "brainstem", "trace_id": "t-a"}
    # Read-only: ни индекс, ни граф не изменились.
    assert facade.index.count() == before_index
    assert facade.graph.stats() == before_graph


def test_default_memory_lazy_import_error(tmp_path, monkeypatch) -> None:
    """Файлов реализаций нет — DefaultMemory честно говорит «ещё не собрана».

    Сами файлы не трогаем и не импортируем: прячем модули через sys.modules.
    """
    monkeypatch.setitem(sys.modules, "memory.vectors", None)
    monkeypatch.setitem(sys.modules, "memory.graph", None)
    with pytest.raises(RuntimeError, match="реализация хранилища ещё не собрана"):
        DefaultMemory(tmp_path / "mem")


# --- G2: смена движка — правкой манифеста, без правки цикла --------------------


def test_engine_swap_via_manifest(tmp_path, manifest_path, journal, gateway) -> None:
    workdir = tmp_path / "memory-workdir"
    for cls_name, cls in (("FakeMemoryA", FakeMemoryA), ("FakeMemoryB", FakeMemoryB)):
        manifest = write_manifest(
            tmp_path, f"manifest-{cls_name}.yaml", manifest_with_memory(f"tests.test_memory_loop:{cls_name}")
        )
        engine = memory_from_manifest(manifest, workdir)

        assert isinstance(engine, cls)
        assert isinstance(engine, Memory)  # протокол памяти удовлетворён
        assert engine.workdir == workdir  # workdir передан адаптеру

        loop = Loop(gateway, journal, memory=engine)
        assert loop.run([step(intent=f"шаг под {cls_name}")]) is True
        assert len(engine.observed) == 1  # цикл работает с каждым движком одинаково
        assert engine.observed[0]["type"] == "reflect"


def test_adapter_without_workdir_parameter(tmp_path) -> None:
    manifest = write_manifest(tmp_path, "bare.yaml", manifest_with_memory("tests.test_memory_loop:FakeMemoryBare"))
    engine = memory_from_manifest(manifest, tmp_path / "mem")
    assert isinstance(engine, FakeMemoryBare)
    assert engine.workdir is None  # инстанцирован без аргументов


def test_manifest_without_memory_organ(tmp_path) -> None:
    path = write_manifest(tmp_path, "no-memory.yaml", copy.deepcopy(MANIFEST))
    assert memory_from_manifest(path, tmp_path / "mem") is None

    # Цикл с memory=None живёт как раньше (см. test_memory_none_keeps_loop_as_before).


@pytest.mark.parametrize("command", [None, "none"])
def test_engine_not_deployed_degrades_to_none(tmp_path, command) -> None:
    manifest = write_manifest(
        tmp_path, f"undeployed-{command}.yaml", manifest_with_memory("tests.test_memory_loop:FakeMemoryA", command=command)
    )
    assert memory_from_manifest(manifest, tmp_path / "mem") is None


def test_broken_adapter_raises_valueerror(tmp_path) -> None:
    manifest = write_manifest(tmp_path, "broken.yaml", manifest_with_memory("tests.no_such_module:FakeMemory"))
    with pytest.raises(ValueError, match="не загрузился"):
        memory_from_manifest(manifest, tmp_path / "mem")


def test_adapter_violating_protocol_raises_valueerror(tmp_path) -> None:
    manifest = write_manifest(tmp_path, "notmemory.yaml", manifest_with_memory("tests.test_memory_loop:NotMemory"))
    with pytest.raises(ValueError, match="протокол Memory"):
        memory_from_manifest(manifest, tmp_path / "mem")


# --- отказной режим: degrade SPEC-0005 -----------------------------------------


def test_broken_memory_degrades_but_loop_finishes(manifest_path, journal, gateway) -> None:
    loop = Loop(gateway, journal, memory=BrokenMemory())

    assert loop.run([step(intent="всё равно работать")]) is True  # эхо-орган ответил
    errors = journal.by_type("error")
    assert len(errors) == 2  # один на context перед PLAN, один на observe после REFLECT
    assert all(e["payload"]["reason"] == "memory_unavailable" for e in errors)
    assert all(e["source"] == "brainstem" for e in errors)

    types = [e["type"] for e in journal.by_trace(journal.all()[0]["trace_id"])]
    assert types == ["error", "plan", "act", "observe", "reflect", "error"]
    (act,) = journal.by_type("act")
    assert act["organ"] == "sense-a"  # шаг исполнен, не смотря на мёртвую память


# --- G3: replay пишет только в переданные движки и не создаёт файлов -----------


def test_replay_creates_no_files_and_uses_passed_engines(manifest_path, tmp_path, gateway) -> None:
    blood = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.attach(blood)
    loop = Loop(gateway, journal, memory=FakeMemory())
    assert loop.run([step(), step()], trace_id="g3") is True
    journal.close()

    index, graph = StubVectorIndex(), StubMemoryGraph()  # фейки файлов не создают
    report = replay(blood, index=index, graph=graph)

    assert report["envelopes"] == len(journal.all())
    assert report["indexed"] == len(index.vectors) == index.count()
    assert report["graph"] == {"nodes": len(graph.nodes), "edges": len(graph.edges)}

    # В tmp_path — только то, что создали тест и фикстуры: манифест и кровь.
    created = {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")}
    assert created == {"mcp-manifest.yaml", "blood.jsonl"}
