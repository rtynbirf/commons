# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмки стыка волн №24–№27 (0.48.2) — перекрёстные, третьим путём.

Дисциплина стыков (волны №18/№23): их база принята целиком, наше зерно вжито
аддитивно, параллельные машины выметены. Эти приёмки меряют СТЫК — то, что
ни одна линия в одиночку не гарантирует:

- словарь типов крови — союз обеих линий (исторический диалект approval.request/
  approval.grant валиден навсегда рядом с их stop.requested/forget);
- два слоя памяти в одном доме: их файловый (MemoryFiles, надгробия) + наш
  движковый (forget по трейсу, trade-снапшот) — и надгробие держит оба (G4);
- сшитый контур: их стоп-нерв и их семантика цены (вопрос = P0, внимание 1;
  вето — без внимания) живут в одном цикле с нашим attention.py;
- якорная книга — союз печатей обеих линий, каждая сходится с живой кровью;
- реестр аксиом (их формат) держит маркеры служения после свивки.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from blood.envelope import Cost, make
from blood.journal import Journal
from blood.olfactory import smell
from brainstem import Budget, Loop, Step
from brainstem.attention import ATTENTION_PRIORITIES
from brainstem.silence import ANSWER_APPROVED, ApprovalRequest, await_approval
from memory.engine import DefaultMemory
from memory.files import MemoryFiles
from memory.replay import replay
from memory.trade import export as trade_export
from memory.trade import import_snapshot
from scripts import doctor

from tests.test_silence import FakeClock, fake_sleep  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


def _ts(shift: float = 0.0) -> str:
    base = datetime(2026, 11, 3, 15, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(seconds=shift)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# --- словарь типов: союз обеих линий -----------------------------------------


def test_schema_dictionary_is_the_union_of_both_lines() -> None:
    schema = json.loads((ROOT / "blood" / "envelope.schema.json").read_text(encoding="utf-8"))
    types = set(schema["properties"]["type"]["enum"])
    # исторический диалект стыка волн №23 (наша кровь) — валидна навсегда
    assert {"approval.request", "approval.grant"} <= types
    # их новые типы (стоп, надгробие) — рядом
    assert {"stop.requested", "forget"} <= types
    # контурный диалект жив
    assert {"approval.requested", "approval.granted", "approval.veto", "approval.expired"} <= types


def test_historical_dialect_blood_still_appends_and_reads() -> None:
    journal = Journal()
    ask = make(
        "approval.request", "pid1", "self", "t1",
        {"what": "шаг", "window_seconds": 60},
        Cost(attention=1), idempotency_key="j30:hist", occurred_at=_ts(0),
        attention_class="P0",
    )
    journal.append(ask)
    journal.append(make(
        "approval.grant", "pid1", "self", "t1",
        {"request_id": ask["id"]}, Cost(), idempotency_key="j30:hist:g",
        causation_id=ask["id"], occurred_at=_ts(1),
    ))
    types = [e["type"] for e in journal.all()]
    assert "approval.request" in types and "approval.grant" in types
    from blood.diary import entries

    report = entries(journal)
    assert report["records"], "дневник читает исторический диалект"


# --- два слоя памяти в одном доме ---------------------------------------------


class _Echo:
    def call(self, organ, tool, payload, trace_id, *, reversibility=None, idempotency_key=None):
        return {"ok": True}


def _house_with_memory(tmp_path: Path) -> tuple[Journal, DefaultMemory, MemoryFiles, str]:
    blood = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.attach(blood)
    journal.append(make("boot", "brainstem", "self", "t-styk", {"start": "стык"}, Cost()))
    memory = DefaultMemory(tmp_path / "mem")
    replay(blood, index=memory.index, graph=memory.graph)
    files = MemoryFiles(index=memory.index, graph=memory.graph, journal=journal, export_dir=tmp_path / "commons-memory")
    return journal, memory, files, blood


def test_both_memory_layers_coexist_and_forget(tmp_path: Path) -> None:
    journal, memory, files, blood = _house_with_memory(tmp_path)
    # живая память: reflect-конверт попадает в оба слоя
    journal.append(make(
        "reflect", "brainstem", "self", "t-styk",
        {"intent": "помнить стык", "satisfied": True, "criterion": "m1"},
        Cost(),
    ))
    from memory.replay import replay as _replay

    _replay(blood, index=memory.index, graph=memory.graph)
    reflect_id = journal.by_type("reflect")[0]["id"]
    exported = files.export()
    assert exported["records"] == 1  # их слой: запись читаема файлом
    snapshot = tmp_path / "snap.json"
    traded = trade_export(memory, snapshot)
    assert traded["items"] == 1  # наш слой: та же запись в снапшоте
    # их forget по id — надгробие в крови
    report = files.forget(reflect_id, reason="стык: их слой", by="human")
    assert report["blood"] == "OUT_OF_CONTROL" and report["files"] == "DELETED"
    # наш forget по трейсу — тот же дом, тот же индекс
    trace_report = forget_trace(memory, "t-styk")
    assert trace_report["blood"]["status"] == "OUT_OF_CONTROL"


def forget_trace(memory: DefaultMemory, trace_id: str) -> dict:
    from memory.forget import forget

    return forget(memory, trace_id=trace_id)


def test_tombstone_holds_against_snapshot_backup(tmp_path: Path) -> None:
    """G4 через слои: забытая по надгробию запись не оживает даже из бэкапа (дыра,
    пойманная живым прогоном стыка, починена аддитивно — skipped_tombstoned)."""
    journal, memory, files, blood = _house_with_memory(tmp_path)
    journal.append(make("reflect", "brainstem", "self", "t-styk", {"intent": "запись", "satisfied": True, "criterion": "m1"}, Cost()))
    from memory.replay import replay as _replay

    _replay(blood, index=memory.index, graph=memory.graph)
    snapshot = tmp_path / "snap.json"
    trade_export(memory, snapshot)
    reflect_id = journal.by_type("reflect")[0]["id"]
    files.forget(reflect_id, reason="надгробие до бэкапа-возврата", by="human")
    tombstones = {
        e["payload"]["forget"]
        for e in journal.all()
        if e.get("type") == "forget" and isinstance(e.get("payload"), dict) and isinstance(e["payload"].get("forget"), str)
    }
    assert reflect_id in tombstones
    memory.index.delete(reflect_id)
    g4 = import_snapshot(memory, snapshot, tombstoned=tombstones)
    assert g4["added"] == 0, "надгробие держит: забытое не оживает из снапшота"
    assert g4["skipped_tombstoned"] == [reflect_id]
    assert g4["tombstones_checked"] is True
    # честная граница: несверившийся импорт называет это поимённо
    unchecked = import_snapshot(memory, snapshot)
    assert unchecked["tombstones_checked"] is False and unchecked["skipped_tombstoned"] is None


# --- сшитый контур: их цена, наш словарь ---------------------------------------


def test_merged_loop_their_price_semantics_with_our_vocabulary() -> None:
    journal = Journal()
    clock = FakeClock()
    verdict = await_approval(
        journal, "t1",
        ApprovalRequest(what="снять прод", window_s=0.4, why="необратимое"),
        lambda q: ANSWER_APPROVED, clock=clock, sleeper=fake_sleep(clock),
    )
    assert verdict == ANSWER_APPROVED
    asked = journal.by_type("approval.requested")[0]
    assert asked["cost"]["attention"] == 1 and asked["attention_class"] == "P0"  # их канон
    assert ATTENTION_PRIORITIES == ("P0", "P1", "P2", "P3")  # наш словарь жив как политика
    # их стоп-нерв в том же цикле
    loop = Loop(_Echo(), journal, stop_check=lambda: "слово Человека", approval_channel=lambda q: None)
    done = loop.run(
        [Step(organ="e", tool="echo", payload={"x": "1"}, intent="после стопа")],
        trace_id="t2", budget=Budget(),
    )
    assert done is False
    stops = journal.by_type("stop.requested")
    assert stops and stops[0]["source"] == "pid1" and stops[0]["cost"]["attention"] == 1


def test_merged_veto_carries_no_attention_their_canonical() -> None:
    journal = Journal()
    loop = Loop(_Echo(), journal)
    done = loop.run(
        [Step(organ="e", tool="echo", payload={"k": "v"}, intent="необратимое", reversibility="irreversible")],
        trace_id="t1", budget=Budget(),
    )
    assert done is False
    veto = journal.by_type("veto")[0]
    assert veto["cost"]["attention"] == 0  # их канон: цену несёт вопрос и стоп, не вето


# --- книги стыка: якорная книга и реестр ---------------------------------------


def test_anchor_book_is_the_union_and_every_seal_verifies() -> None:
    from blood.envelope import canonical_sha256

    anchors = [json.loads(l) for l in (ROOT / "blood" / "anchors.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(anchors) >= 12, "печати обеих линий в одной книге"
    files_seen: set[str] = set()
    for a in anchors:
        path = ROOT / a["file"]
        assert path.exists(), f"печать в никуду: {a['file']}"
        events = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(events) == a["events"], a["file"]
        assert canonical_sha256(events[-1]) == a["last_sha256"], a["file"]
        files_seen.add(a["file"])
    assert "runs/2026-11-03-wave30-junction/blood.jsonl" in files_seen, "кровь стыка опечатана"


def test_axioms_registry_holds_markers_after_the_junction() -> None:
    ok, fleas = doctor.check_axioms(ROOT)
    axioms_fleas = [f for f in fleas if f.startswith("docs/axioms.yaml")]
    assert axioms_fleas == [], axioms_fleas[:4]
    import yaml

    registry = yaml.safe_load((ROOT / "docs" / "axioms.yaml").read_text(encoding="utf-8"))
    rows = {r["id"]: r for r in registry["axioms"]}
    assert rows["A19"]["status"] == "СЛУЖЕНО" and rows["A20"]["status"] == "СЛУЖЕНО"
    assert rows["A21"]["status"] == "НЕ СЛУЖЕНО" and rows["A21"]["todo"].startswith("ТЗ-")


def test_smell_reads_merged_house_blood() -> None:
    smells = smell(ROOT / "runs" / "2026-11-03-wave30-junction" / "blood.jsonl")
    assert isinstance(smells, list)  # нюх нашей линии живёт поверх крови стыка
