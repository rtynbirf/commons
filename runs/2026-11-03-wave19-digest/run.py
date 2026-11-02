# Живой прогон волны №19 (Ф-1): выжимка крови — недельный агрегат (W-0019).
# Дата: 2026-11-03. Выжимка читает ВСЮ живую кровь дома (runs/*/blood.jsonl,
# свой каталог исключён) и рендерит output.md — «понял / болело / закрыл / пахнет»;
# собственная кровь прогона — в blood.jsonl.
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.digest import render_digest, week_digest  # noqa: E402
from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, verify  # noqa: E402

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
TRACE = "wave19-digest"

journal = Journal()
journal.attach(JOURNAL)

journal.append(make(
    event_type="boot",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "role": "волна №19 — Ф-1 Мембраны: выжимка крови, недельный агрегат (W-0019)",
        "scope": "SPEC-0003 v0.10.0 п.13; blood/digest.py; понял/болело/закрыл/пахнет; окно по записи, вне окна — названо",
        "repo_base_commit": "a927f78",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))

blood_files = sorted(
    p for p in (REPO_ROOT / "runs").glob("*/blood.jsonl") if p.parent != HERE
)
journal.append(make(
    event_type="act",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "house-digest",
        "files_scanned": len(blood_files),
        "method": "blood.digest.week_digest по всем живым файлам крови дома, свой каталог исключён",
        "read_only": True,
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))

digest_text = render_digest(blood_files)
summary = week_digest(blood_files)
(HERE / "output.md").write_text(digest_text, encoding="utf-8")

journal.append(make(
    event_type="act",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "digest-render",
        "events_in_window": summary["events"],
        "outside_window_named": summary["outside_window"],
        "refusals_total": summary["ached"]["refusals_total"],
        "traces_closed": summary["closed"]["closed"],
        "traces_open": summary["closed"]["open"],
        "smells": summary["smells"],
        "price": summary["price"],
        "verdict": "выжимка отрендерена в output.md — Человеку не нужно читать 30+ jsonl глазами",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))

journal.append(make(
    event_type="reflect",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "verdict": "выжимка служена: кровь дома агрегирована честно — понял/болело/закрыл/пахнет",
        "honesty": "окно по записи; события вне окна названы счётчиком, не спрятаны; проекция не переписывает кровь",
        "tests": "tests/test_blood_digest.py — 11 приёмок; полный сюит зелёный",
        "next": "W-0024 — обратимость честным языком (классы, компенсатор с идемпотентным ключом, approval до факта)",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
    idempotency_key="wave19-digest-reflect",
))

journal.close()

report = verify(JOURNAL)
print(json.dumps(report, ensure_ascii=False, indent=2))
print("output.md:", len(digest_text), "символов")
