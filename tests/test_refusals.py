"""Приёмки счётчика честных отказов — W-0021 (Ф-0.3, волна №16).

Гейт ревизии: «приёмка на живых фактах (B-группа А/Б, NO_SERVER)» —
счётчик проверяется на пролитой крови живых прогонов, а не на синтетике:
runs/2026-11-02-wave10-ab-live — B-группа честного А/Б, где контролируемая
группа провалилась, и её провалы обязаны быть сочтены.
"""

from __future__ import annotations

import json
from pathlib import Path

from blood.envelope import Cost, make
from blood.journal import Journal
from blood.refusals import REFUSAL_TYPES, count_refusals

REPO_ROOT = Path(__file__).resolve().parents[1]
AB_LIVE_BLOOD = REPO_ROOT / "runs/2026-11-02-wave10-ab-live/blood.jsonl"


def test_living_ab_blood_refusals_are_counted() -> None:
    """Живой факт: B-группа А/Б провалилась — счётчик обязан это увидеть."""
    assert AB_LIVE_BLOOD.exists(), "живая кровь А/Б потерялась — это факт дома"
    report = count_refusals(AB_LIVE_BLOOD)
    assert report["total"] > 0, "в крови А/Б есть error/halt/veto — счётчик ослеп"
    # Честная перекрёстная проверка: независимый пересчёт тем же законом.
    naive = 0
    for line in AB_LIVE_BLOOD.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        envelope = json.loads(line)
        if envelope.get("type") in REFUSAL_TYPES:
            naive += 1
    assert report["total"] == naive
    assert set(report["by_type"]) <= set(REFUSAL_TYPES)


def test_non_refusals_do_not_count() -> None:
    """plan/act/observe/reflect/boot/shutdown/organ.* — не отказы."""
    journal = Journal()
    for event_type in ("plan", "act", "observe", "reflect", "boot", "shutdown", "organ.health"):
        journal.append(
            make(
                event_type=event_type,
                source="brainstem",
                organ="self",
                trace_id="refusals-clean",
                payload={},
                cost=Cost(),
            )
        )
    report = count_refusals(journal)
    assert report["total"] == 0
    assert report["by_type"] == {}


def test_refusal_types_are_counted_by_type_and_trace() -> None:
    """Каждый класс отказа считается поимённо, трасса видна."""
    journal = Journal()
    for event_type in ("veto", "halt", "error", "security.violation", "error"):
        journal.append(
            make(
                event_type=event_type,
                source="brainstem",
                organ="self",
                trace_id="refusals-mixed",
                payload={},
                cost=Cost(),
            )
        )
    report = count_refusals(journal)
    assert report["total"] == 5
    assert report["by_type"] == {
        "veto": 1,
        "halt": 1,
        "error": 2,
        "security.violation": 1,
    }
    assert report["traces"] == {"refusals-mixed": 5}


def test_broken_lines_are_named_not_swallowed(tmp_path) -> None:
    """Битая строка — честный skipped, не молчание (закон Journal.skipped)."""
    path = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.attach(path)
    journal.append(
        make(
            event_type="veto",
            source="brainstem",
            organ="self",
            trace_id="refusals-broken",
            payload={"reason": "нет"},
            cost=Cost(),
        )
    )
    journal.close()
    with path.open("a", encoding="utf-8") as fh:
        fh.write("это не json\n")
    report = count_refusals(path)
    assert report["total"] == 1
    assert report["skipped"] == 1


def test_all_living_blood_counts_without_exception() -> None:
    """Счётчик не ослепнет ни на одном живом файле крови дома."""
    runs = REPO_ROOT / "runs"
    files = sorted(runs.glob("*/blood.jsonl"))
    assert files, "кровь дома потерялась"
    for path in files:
        report = count_refusals(path)
        assert isinstance(report["total"], int)
        assert set(report["by_type"]) <= set(REFUSAL_TYPES)
        assert report["skipped"] >= 0
