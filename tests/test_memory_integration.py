"""Интеграционные приёмки памяти 0.6.0: реальный стек по SPEC-0005.

В отличие от tests/test_memory_loop.py (фейки) и tests/test_memory_storage.py
(движки по отдельности) здесь работает весь стек: SQLiteVectorIndex +
MemoryGraph + MemoryFacade/DefaultMemory + ствол мозга + replay крови.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from blood.journal import Journal
from brainstem import Budget, Loop
from memory import Memory
from memory.engine import DefaultMemory, memory_from_manifest
from memory.replay import replay
from synapse.gateway import Gateway
from tests.conftest import MANIFEST, step


class AltMemory:
    """Альтернативный движок для G2: другой класс, тот же протокол."""

    def __init__(self, workdir: Path | None = None) -> None:
        self.workdir = workdir
        self.observed: list[str] = []
        self.contexts: list[str] = []

    def observe(self, envelope: dict) -> None:
        self.observed.append(envelope["id"])

    def context(self, intent: str, k: int = 3) -> list[dict]:
        self.contexts.append(intent)
        return [{"id": "alt-recall", "score": 1.0, "meta": {"engine": "alt"}}]


def _manifest_with_memory(adapter: str, tmp_path: Path) -> Path:
    """Манифест с органом памяти system: memory (SPEC-0005 п.2)."""
    entry = {
        "name": "memory-baseline",
        "system": "memory",
        "mode": "dependency",
        "upstream": "own code (memory/)",
        "license": "Apache-2.0",
        "transport": "internal",
        "command": "memory-engine",
        "healthcheck": "facade contract",
        "tools": ["observe", "context"],
        "authority": {"fs": "workdir", "network": "none"},
        "adapter": adapter,
    }
    raw = {**MANIFEST, "organs": [*MANIFEST["organs"], entry]}
    path = tmp_path / "manifest-memory.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return path


def test_g1_replay_equals_live_memory(manifest_path, journal, tmp_path) -> None:
    """G1 SPEC-0005: пустой движок + replay крови эквивалентен живой памяти."""
    live = DefaultMemory(tmp_path / "live")
    loop = Loop(Gateway(manifest_path, journal), journal, memory=live)
    loop.run([step()], budget=Budget())

    journal.to_jsonl(tmp_path / "blood.jsonl")
    live.index.flush()
    live.graph.flush()

    replayed = DefaultMemory(tmp_path / "replayed")
    report = replay(tmp_path / "blood.jsonl", index=replayed.index, graph=replayed.graph)

    assert report["envelopes"] == len(journal)
    assert report["indexed"] == len(journal.by_type("reflect"))  # SPEC-0005 п.1
    assert report["skipped"] == 0
    assert report["graph"]["nodes"] == replayed.graph.stats()["nodes"]

    intent = step().intent
    live_hits = live.context(intent, k=3)
    replayed_hits = replayed.context(intent, k=3)
    assert live_hits, "живая память должна помнить сессию"
    # Эквивалентность: тот же топ-конверт и та же цена сходства — вектора считались
    # по одному правилу (memory.replay.envelope_text) и вживую, и при replay.
    assert [h["id"] for h in live_hits] == [h["id"] for h in replayed_hits]
    assert pytest.approx(live_hits[0]["score"], abs=1e-9) == replayed_hits[0]["score"]


def test_g2_engine_swap_by_manifest(manifest_path, journal, tmp_path) -> None:
    """G2 SPEC-0005: смена движка памяти — правкой манифеста, без кода цикла."""
    first = memory_from_manifest(_manifest_with_memory("memory.engine:DefaultMemory", tmp_path), tmp_path / "w1")
    assert isinstance(first, Memory)
    loop = Loop(Gateway(manifest_path, journal), journal, memory=first)
    loop.run([step()], budget=Budget())
    first.index.flush()
    first.graph.flush()
    assert (tmp_path / "w1" / "vectors.sqlite").exists()
    assert (tmp_path / "w1" / "graph.jsonl").exists()

    second = memory_from_manifest(_manifest_with_memory("tests.test_memory_integration:AltMemory", tmp_path), tmp_path / "w2")
    assert isinstance(second, AltMemory)
    journal2 = Journal()
    loop2 = Loop(Gateway(manifest_path, journal2), journal2, memory=second)
    loop2.run([step()], budget=Budget())
    assert second.observed, "альтернативный движок получил конверты после REFLECT"
    assert second.contexts == [step().intent]
    assert len(second.observed) == len(journal2.by_type("reflect"))  # SPEC-0005 п.1: только reflect


def test_g2_memory_not_declared(manifest_path, tmp_path) -> None:
    """Манифест без system: memory → None: цикл живёт без памяти (degrade)."""
    assert memory_from_manifest(manifest_path, tmp_path) is None


def test_g3_memory_files_only_in_workdir(manifest_path, journal, tmp_path) -> None:
    """G3 SPEC-0005: данные памяти — только в переданном workdir, локально."""
    engine = DefaultMemory(tmp_path / "wd")
    loop = Loop(Gateway(manifest_path, journal), journal, memory=engine)
    loop.run([step()], budget=Budget())
    engine.index.flush()
    engine.graph.flush()
    created = {p.name for p in (tmp_path / "wd").iterdir()}
    assert created == {"vectors.sqlite", "graph.jsonl"}


def test_replay_of_repository_first_pulse(tmp_path) -> None:
    """Кровь — истина: первая пульсация репозитория восстанавливается в память."""
    blood = Path(__file__).resolve().parents[1] / "runs" / "2026-11-01-first-pulse" / "blood.jsonl"
    assert blood.exists(), "артефакт первого пульса должен быть в репо"
    engine = DefaultMemory(tmp_path / "pulse")
    report = replay(blood, index=engine.index, graph=engine.graph)
    assert report["envelopes"] == 4  # plan → act → observe → reflect
    assert report["skipped"] == 0
    assert report["graph"]["nodes"] > 0
    hits = engine.context("преобразуй документ в markdown", k=1)
    assert hits and hits[0]["score"] > 0.0


def test_replay_honest_on_broken_lines(tmp_path) -> None:
    """Битые строки крови не роняют replay — счётчик skipped честен."""
    blood = tmp_path / "broken.jsonl"
    good = {"id": "e1", "ts": "2026-11-02T00:00:00Z", "type": "plan", "source": "brainstem",
            "organ": "none", "trace_id": "t1", "payload": {"intent": "дело"}, "cost": {"tokens_in": 0, "tokens_out": 0, "seconds": 0.0}}
    blood.write_text(
        json.dumps(good, ensure_ascii=False) + "\n"
        + "не-json-строка\n"
        + json.dumps({"мусор": True}) + "\n",
        encoding="utf-8",
    )
    engine = DefaultMemory(tmp_path / "wd")
    report = replay(blood, index=engine.index, graph=engine.graph)
    assert report["envelopes"] == 1
    assert report["skipped"] == 2
