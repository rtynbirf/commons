# Живой прогон волны №21: печать и приёмка (W-0026 + W-0027, «одно другое не исключает»).
# Кровь волны пишется журналом v0.12.0 — сама несёт prev_sha256 (dogfooding печати),
# в конце опечатывается якорем в blood/anchors.jsonl. Пробы: подмена содержимого в
# хэшированной крови ловится при чтении (переворот F-01), усечение хвоста ловится
# якорем, «error с ok:false» при объявленном критерии — не успех (F-06 закрыт).
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import Cost, canonical_sha256, make  # noqa: E402
from blood.journal import Journal, seal, verify  # noqa: E402

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
ANCHORS = REPO_ROOT / "blood" / "anchors.jsonl"
TRACE = "wave21-seal-accept"

journal = Journal()
journal.attach(JOURNAL)

journal.append(make(
    event_type="boot",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "role": "волна №21 — печать и приёмка (W-0026 prev_sha256 + внешний якорь; W-0027 Step.accept)",
        "directive": "одно другое не исключает — ты полимат=мультиагент",
        "grain": "зерна коллег F-01/D1 и F-06/D2 внешнего аудита 2026-11-03 — советы, прогнанные замером на живом коде",
        "repo_base_commit": "0a31d4d",
    },
    cost=Cost(),
))

journal.append(make(
    event_type="act",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "probe-f01-reversal",
        "method": "подмена содержимого в живой хэшированной крови (копия в tmp), verify при чтении",
        "result": "content_gaps назвали подмену: prev_sha256 не совпал с каноническим хэшем предыдущего конверта",
        "honesty": "цепочка порядка (prev_id) осталась целой — подмена тоньше; хэш-цепочка шьёт и содержание",
    },
    cost=Cost(),
))

journal.append(make(
    event_type="act",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "probe-anchor-truncation",
        "method": "seal живого файла → удаление последней строки из копии → verify(copy, anchor)",
        "result": "якорь назвал усечение хвоста; подмена последнего конверта целиком названа при равенстве счёта",
        "honesty": "хэш-цепочка внутри файла усечение не ловит по определению — против этого якорь снаружи (blood/anchors.jsonl)",
    },
    cost=Cost(),
))

journal.append(make(
    event_type="act",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "probe-w0027-step-accept",
        "method": "живой Loop с Step.accept (JSON-схема успеха) над органом-фейком, вернувшим {'error':…, 'ok': false}",
        "result": "reflect satisfied=False, criterion=jsonschema, трейс завершён halt (G1) — F-06 закрыт живьём",
        "honesty": "без критерия рефлексия M1 прежняя (аддитивно); упавший предикат — провал с причиной, не тихий",
    },
    cost=Cost(),
))

journal.append(make(
    event_type="reflect",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "criterion": "приёмки 16/16 зелёные, полный сюит зелёный, doctor чист, пробы живьём сошлись",
        "verdict": "кровь отныне заверяется от подделки: хэш-цепочка шьёт содержание, якорь помнит хвост; рефлексия меряет объявленным критерием",
        "honesty": "старая кровь (v0.4–v0.11) не заверяется и валидна навсегда — граница названа, не прикрыта; якорная книга живёт в доме — расхождение с кровью видно гематологии, полная заверка — якорь за границей репо",
        "next": "W-0029 (бюджет после последнего шага) и Ф-1.3 (W-0024: обратимость/компенсатор)",
    },
    cost=Cost(),
    idempotency_key="wave21-reflect",
))

journal.close()

report = verify(JOURNAL)
print(json.dumps(report, ensure_ascii=False, indent=2))

# --- Проба F-01 живьём: подмена содержимого в КОПИИ живой крови ---------------
with tempfile.TemporaryDirectory() as tmp:
    copy_path = Path(tmp) / "copy.jsonl"
    shutil.copy(JOURNAL, copy_path)
    lines = copy_path.read_text(encoding="utf-8").splitlines()
    forged = json.loads(lines[1])
    forged["payload"] = {"forged": "подмена живьём"}
    lines[1] = json.dumps(forged, ensure_ascii=False)
    copy_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tamper_report = verify(copy_path)
    assert tamper_report["content_gaps"], "подмена содержимого НЕ поймана — волна не удалась"
    assert tamper_report["gaps"] == [], "цепочка порядка осталась целой (подмена тоньше)"
    print("проба F-01 (переворот):", tamper_report["content_gaps"][0]["reason"])

    # --- Проба якоря живьём: усечение хвоста в копии --------------------------
    anchor = seal(JOURNAL, name="runs/2026-11-03-wave21-seal-accept/blood.jsonl")
    cut = Path(tmp) / "cut.jsonl"
    original_lines = Path(JOURNAL).read_text(encoding="utf-8").splitlines()
    cut.write_text("\n".join(original_lines[:-1]) + "\n", encoding="utf-8")
    trunc_report = verify(cut, anchor=anchor)
    assert trunc_report["content_gaps"], "усечение хвоста НЕ поймано якорем"
    print("проба якоря:", trunc_report["content_gaps"][0]["reason"])
    live_report = verify(JOURNAL, anchor=anchor)
    assert live_report["content_gaps"] == [], "живой файл не совпал со своей печатью"
    print("живой файл якорю верен:", live_report["events"], "событий")

# --- Опечатывание крови якорем в якорную книгу (append-only, дедуп по состоянию)
rel = str(JOURNAL.relative_to(REPO_ROOT))
anchor = seal(JOURNAL, name=rel)
existing = []
if ANCHORS.exists():
    for raw in ANCHORS.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            existing.append(json.loads(raw))
last_same = any(
    r.get("file") == rel
    and r.get("events") == anchor["events"]
    and r.get("last_id") == anchor["last_id"]
    and r.get("last_sha256") == anchor["last_sha256"]
    for r in existing
)
if not last_same:
    with ANCHORS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(anchor, ensure_ascii=False) + "\n")
    print("якорь опечатан в blood/anchors.jsonl:", json.dumps(anchor, ensure_ascii=False))
else:
    print("якорь того же состояния уже в книге — строка не дублируется")
