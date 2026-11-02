# Стык-забег такта 2 волны №18: их дневник (0.37.0, a927f78) над всей кровью дома.
# Кровь blood.jsonl записана параллельным прогоном ДО стыка (реализацией, выметенной
# по стык-дисциплине) — конверты валидны, остаются вещественным доказательством;
# проекции строятся принятым базой дневником.
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.diary import entries, render, to_jsonl  # noqa: E402

HERE = Path(__file__).resolve().parent
OWN = HERE / "blood.jsonl"
W17_ORIGIN = REPO_ROOT / "runs" / "2026-11-03-wave17-origin" / "blood.jsonl"
W17_MEMBRANE = REPO_ROOT / "runs" / "2026-11-03-wave17-membrane-blood" / "blood.jsonl"

failures: list[str] = []


def check(name: str, ok: bool, detail: str) -> None:
    if not ok:
        failures.append(f"{name}: {detail}")


# --- их дневник над тремя стилями живой крови дома
before = hashlib.sha256(OWN.read_bytes()).hexdigest()
own_md = HERE / "diary.md"
own_md.write_text(render(OWN), encoding="utf-8")
own_jl = to_jsonl(OWN, HERE / "diary.jsonl")
after = hashlib.sha256(OWN.read_bytes()).hexdigest()

check("blood_untouched", before == after, "дневник не переписывает кровь (контрольная сумма)")

book = entries(OWN)
check("own_digest", len(book["records"]) == 12 and book["broken_lines"] == 0, "12 конвертов — 12 записей, 0 битых строк")
check("own_no_gaps", book["damaged"] == [], "цепочка целa")
unfulfilled = book["plans_unfulfilled"]
check("own_plan_honesty", unfulfilled == 2, "veto-план сети и halt-план сжатия — 2 плана без причинного исполнения")

md_text = own_md.read_text(encoding="utf-8")
jl_rows = [json.loads(l) for l in own_jl.read_text(encoding="utf-8").splitlines() if l.strip()]
check("no_success_word", "успешно" not in md_text.lower(), "слово-обещание дневнику запрещено")
check("jsonl_two_traces", len(jl_rows) == 2 and all({"trace_id", "records", "totals"} <= set(r) for r in jl_rows), "JSONL — одна строка на трейс")
check("undo_not_promised", "не обещается" in md_text, "отмена не обещается (W-0024)")

for name, path in [("wave17-origin", W17_ORIGIN), ("wave17-membrane", W17_MEMBRANE)]:
    b = entries(path)
    text = render(path)
    check(f"{name}_digest", b["damaged"] == [] and len(b["records"]) > 0, "чужая живая кровь дневнуется как есть")
    check(f"{name}_honest", "успешно" not in text.lower(), "слово-обещание не протекло")
    to_jsonl(path, HERE / f"diary-{name}.jsonl")
    (HERE / f"diary-{name}.md").write_text(text, encoding="utf-8")

if failures:
    print(f"КРАСНО: {len(failures)} провал(ов)")
    for f in failures:
        print(" -", f)
    sys.exit(1)

print("ЧИСТО: стык-забег такта 2 — их дневник над всей кровью дома")
print(f"своя кровь: {len(book['records'])} записей, планов без исполнения {unfulfilled}, 0 гэпов")
print(f"кровь волны №17 (origin): {len(entries(W17_ORIGIN)['records'])} записей")
print(f"адаптерная кровь их такта 2: {len(entries(W17_MEMBRANE)['records'])} записей")
print(f"экспорт: diary.md ({own_md.stat().st_size} Б), diary.jsonl ({own_jl.stat().st_size} Б) + diary-wave17-origin.* + diary-wave17-membrane.*")
