# Живой прогон волны №26 (0.45.0): оценка пути (W-0020, SPEC-0003 п.18)
# и нюх крови (Ф-2.3, SPEC-0003 п.19). Сцены: синтетический путь с переигркой
# назван восстановленным; живой свип пути по всей крови дома; живой свип нюха
# по всем файлам крови дома; открытые трейсы названы, не спрятаны. Кровь
# проливает сам дом — органов в прогоне нет (проекции read-only).
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, seal, verify  # noqa: E402
from blood.olfactory import smell_all  # noqa: E402
from blood.path import path_of, render  # noqa: E402

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
TRACE = "wave26-path-olfactory"

journal = Journal()
journal.attach(JOURNAL)

journal.append(make(
    event_type="boot",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "role": "волна №26 (0.45.0): оценка пути (W-0020, SPEC-0003 п.18, Ф-2.7) + нюх крови (Ф-2.3, SPEC-0003 п.19)",
        "directive": "путь, переживший отказ и восстановленный, обязан быть назван; запахи крови — измеримые сигналы, названные вслух",
        "honesty": "органов в прогоне нет — волна о проекциях read-only; кровь проливает сам дом",
    },
    cost=Cost(),
))

# --- Сцена 1: путь с провалом и восстановлением назван честно -------------------
demo = Journal()
demo_trace = "wave26-demo-recovered"
plan = demo.append(make("plan", "brainstem", "echo-a", demo_trace, {"what": "пробная задача"}, Cost()))
demo.append(make("error", "brainstem", "echo-a", demo_trace, {"reason": "первая попытка упала"}, Cost()))
demo.append(make("act", "brainstem", "echo-a", demo_trace, {"what": "повтор"}, Cost(), causation_id=plan["id"]))
demo.append(make("reflect", "brainstem", "echo-a", demo_trace, {"verdict": "готово"}, Cost()))
p = path_of(list(demo.by_trace(demo_trace)))
text = render(p)
assert p["failures"] == 1 and p["retries"] == 1 and p["recovered"] and not p["smooth"]
assert "успешно" not in text.lower() and "восстановлен" in text.lower()

def _smoke_event(kind: str, step: int, scene: str, result: str) -> None:
    journal.append(make(
        event_type="observe",
        source="brainstem",
        organ="self",
        trace_id=TRACE,
        payload={"step": step, "scene": scene, "result": result},
        cost=Cost(),
    ))

_smoke_event("observe", 1, "синтетический путь: провал → переигрка → восстановление названы",
             f"провалов 1, переигрок 1, восстановлен; «успешно» не написано: {text[:60]}…")

# --- Сцена 2: живой свип пути по всей крови дома --------------------------------
files = sorted((REPO_ROOT / "runs").glob("**/blood.jsonl"))
outcomes = {"reflect", "halt", "open"}
traces_seen = 0
recovered = 0
open_traces = 0
for path in files:
    events = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    by_trace: dict[str, list[dict]] = {}
    for e in events:
        if isinstance(e, dict) and e.get("trace_id"):
            by_trace.setdefault(e["trace_id"], []).append(e)
    for tid, evs in by_trace.items():
        pp = path_of(evs)
        assert pp["outcome"] in outcomes, (path, tid, pp)
        traces_seen += 1
        recovered += 1 if pp["recovered"] else 0
        open_traces += 1 if pp["outcome"] == "open" else 0
_smoke_event("observe", 2, "живой свип пути по всей крови дома",
             f"файлов {len(files)}, трейсов {traces_seen}, восстановленных {recovered}, открытых {open_traces}")

# --- Сцена 3: живой свип нюха по всем файлам крови дома --------------------------
report = smell_all(REPO_ROOT)
noisy = {rel: s for rel, s in report.items() if s}
top = sorted(noisy.items(), key=lambda kv: -len(kv[1]))[:3]
top_text = "; ".join(f"{rel}: {len(s)} запахов" for rel, s in top) if top else "тихо"
_smoke_event("observe", 3, "живой свип нюха по всему дому",
             f"файлов понюхано {len(report)}, с запахами {len(noisy)}; громче всех — {top_text}")

# --- Сцена 4: открытые трейсы названы, не спрятаны --------------------------------
opens = [(rel, s) for rel, s in noisy.items() for smell_line in s if "открытых трейсов" in smell_line]
count_opens = sum(int(s.split(": ")[1].split(" ")[0]) for _, s in opens for s in s if "открытых трейсов" in s) if opens else 0
_smoke_event("observe", 4, "открытые трейсы названы вслух",
             f"файлов с открытыми трейсами: {len(opens)}, открытых трейсов: {count_opens} — названы, не спрятаны")

# --- Печать и сверка своей крови ------------------------------------------------
anchor = seal(JOURNAL)
report_verify = verify(JOURNAL, anchor=anchor)
assert report_verify["gaps"] == [] and report_verify["content_gaps"] == [] and report_verify["skipped"] == 0, report_verify
envelopes = journal.by_trace(TRACE)
print(f"WAVE26: {len(envelopes)} конвертов, 0 гэпов, chained + hashed, опечатана якорем; "
      f"трейсов оценено {traces_seen}, файлов понюхано {len(report)}")
