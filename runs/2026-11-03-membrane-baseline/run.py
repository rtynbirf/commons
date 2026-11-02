# Кровотечение Этапа 0 (baseline пакета Human Membrane v0.1.0).
# Два конверта: baseline.started / baseline.completed. Цепочка prev_id — от журнала.
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, verify

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
TRACE = "membrane-baseline"

journal = Journal()
journal.attach(JOURNAL)

journal.append(make(
    event_type="boot",
    source="membrane-baseline",
    organ="selfmap",
    trace_id=TRACE,
    payload={
        "package": "COMMONS_Human_Membrane_Implementation_Package_v0.1.0.zip",
        "package_integrity": "sha256 MANIFEST OK",
        "repo_commit": "7f048ec",
        "stage": "roadmap stage 0",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))

journal.append(make(
    event_type="act",
    source="membrane-baseline",
    organ="selfmap",
    trace_id=TRACE,
    payload={
        "points": 21,
        "repo_fact": 10,
        "not_built": 8,
        "partial": 1,
        "dictionary_conflict": 1,
        "unknown_inside_fact": 1,
        "baseline_tests": "519 passed in 14.82s",
        "next": "PR-1 blood adapter",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))

journal.close()

verdict = verify(JOURNAL)
print(json.dumps(verdict, ensure_ascii=False))
print(f"конвертов: {verdict.get('envelopes', verdict)}")
