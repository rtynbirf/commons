# Кровотечение ревизии ревизора (2026-11-03): boot → act.
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, verify  # noqa: E402

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
TRACE = "revision-full"

journal = Journal()
journal.attach(JOURNAL)

journal.append(make(
    event_type="boot",
    source="revision",
    organ="selfmap",
    trace_id=TRACE,
    payload={
        "role": "polymath-arbiter-auditor-revisor",
        "scope": "проект вдоль и поперёк + мировые практики + ТЗ шлейфа",
        "repo_commit": "02f4d56",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))

journal.append(make(
    event_type="act",
    source="revision",
    organ="selfmap",
    trace_id=TRACE,
    payload={
        "verdict": "см. REVISION.md рядом",
        "acceptance_matrix_A01_A25": {"pass": 5, "partial": 4, "not_built": 14, "adr": 2},
        "wave5_red_findings": "5/5 закрыты — подтверждено",
        "world_check": "обгоняем: supply chain, песочницы, rogue-метод, llms.txt; отстаём: память/consolidation, dispatcher, approval, дневник/undo",
        "roadmap": {"F0": 5, "F1": 5, "F2": 7, "F3": 4, "F_donors": 5},
        "donor_points_live": "7 точек сверены живым API 2026-11-02T19:5xZ",
        "next": "Ф-0 гигиена шлейфа → волна №15 Мембрана (PR-1, PR-2)",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))

journal.close()

print(json.dumps(verify(JOURNAL), ensure_ascii=False))
