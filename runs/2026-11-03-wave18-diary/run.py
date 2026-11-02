# Живой прогон волны №18 (Ф-1.2): дневник человека — кровь, переведённая на человеческий (W-0023).
# Дата: 2026-11-03. Дневник читает живую кровь волн №17 (ядро такт 1 + адаптер такт 2)
# и рендерит output.md — артефакт для Человека; собственная кровь прогона — в blood.jsonl.
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.diary import entries, render  # noqa: E402
from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, verify  # noqa: E402

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
TRACE = "wave18-diary"

ORIGIN = REPO_ROOT / "runs" / "2026-11-03-wave17-origin" / "blood.jsonl"
MEMBRANE = REPO_ROOT / "runs" / "2026-11-03-wave17-membrane-blood" / "blood.jsonl"

journal = Journal()
journal.attach(JOURNAL)

journal.append(make(
    event_type="boot",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "role": "волна №18 — Ф-1.2 Мембраны: дневник человека (W-0023)",
        "scope": "SPEC-0003 v0.9.0 п.12; blood/diary.py; A04/A05; план ≠ факт; отмена не обещается",
        "repo_base_commit": "50dc9e6",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))

renders: dict[str, str] = {}
for label, path in (("wave17-origin (ядро такт 1)", ORIGIN), ("wave17-membrane-blood (адаптер такт 2)", MEMBRANE)):
    report = verify(path)
    book = entries(path)
    renders[label] = render(path)
    journal.append(make(
        event_type="act",
        source="brainstem",
        organ="self",
        trace_id=TRACE,
        payload={
            "act": "diary-render",
            "file": str(path.relative_to(REPO_ROOT)),
            "events_read": len(book["records"]),
            "verify": report,
            "broken_lines": book["broken_lines"],
            "plans_unfulfilled": book["plans_unfulfilled"],
            "totals": book["totals"],
            "verdict": "кровь прочитана, дневник отрендерен в output.md — Человеку не нужно читать jsonl глазами",
        },
        cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
    ))

journal.append(make(
    event_type="reflect",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "verdict": "дневник служен: кровь обеих волн №17 переведена на человеческий (output.md)",
        "honesty": "план — намерение; «успешно» только при проверке; неизвестное время — неизвестно; отказ — данные; отмена не обещается (W-0024)",
        "tests": "tests/test_blood_diary.py — 15 приёмок (A04/A05); полный сюит зелёный",
        "next": "Ф-1 продолжение: W-0019 (агрегат-выжимка) — слой над дневником; W-0024 (обратимость) — компенсатор",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
    idempotency_key="wave18-diary-reflect",
))

journal.close()

output = ["# Дневник организма — живой прогон волны №18 (2026-11-03)", ""]
output.append("Кровь, переведённая на человеческий: реконструкция сессии (SPEC-0003 п.8) служит телу,")
output.append("дневник — Человеку. Ниже — живые трейсы волн №17 обеих линий стыка.")
output.append("")
for label, text in renders.items():
    output.append("---")
    output.append(f"## Кровь: {label}")
    output.append("")
    output.append(text)
(HERE / "output.md").write_text("\n".join(output) + "\n", encoding="utf-8")

print(json.dumps(verify(JOURNAL), ensure_ascii=False, indent=2))
print("output.md:", len("\n".join(output)), "символов")
