# Живой прогон волны №29 (контур обмена: docs/TZ.md ТЗ-2.4, ТЗ-2.5, ТЗ-3.1).
# Дата: 2026-11-03. Красный прогон зафиксирован: 3 failed (make без path,
# ADR-0016 отсутствовал, приёмка транспорта красила живой факт дома —
# http-органы; честный ADR написан по факту: stdio + localhost-http).
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, seal, verify  # noqa: E402
from brainstem.dispatch import DLQ, DONE, SHED, TIMEOUT, Dispatcher  # noqa: E402

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
TRACE = "wave29-dispatch"

if JOURNAL.exists():
    JOURNAL.unlink()

journal = Journal()
journal.attach(JOURNAL)
results: dict[str, dict] = {}
d = Dispatcher(journal, max_attempts=3)

# --- ТЗ-2.4: доставка живьём ----------------------------------------------------

done = d.deliver("live-ok", lambda: {"резюме": "кровь цела"}, label="резюме недели")
assert done["verdict"] == DONE and done["attempts"] == 1

calls = {"n": 0}


def flaky() -> dict:
    calls["n"] += 1
    if calls["n"] < 3:
        raise OSError("канал дёрнулся")
    return {"выжил": True}


survived = d.deliver("live-flaky", flaky, label="живучее поручение")
assert survived["verdict"] == DONE and survived["attempts"] == 3
retry_report = d.deliver("live-flaky", flaky, label="живучее поручение")
assert retry_report["redelivered"] is True and calls["n"] == 3, "повтор ключа не повторяет эффект (A01)"

dead = d.deliver("live-dead", lambda: (_ for _ in ()).throw(RuntimeError("орган мёртв")), label="мёртвое поручение")
assert dead["verdict"] == DLQ and dead["attempts"] == 3
assert d.dead_letters() and d.dead_letters()[-1]["payload"]["delivery"]["label"] == "мёртвое поручение"

full = {"t": 100.0}
slow_d = Dispatcher(journal, timeout=1.0, clock=lambda: full["t"])
timed = slow_d.deliver("live-slow", lambda: (full.__setitem__("t", full["t"] + 5.0), {"поздно": True})[1], label="медленное поручение")
assert timed["verdict"] == TIMEOUT and "дедлайн" in timed["reason"]

queue_d = Dispatcher(journal, max_queue=2)
queue_d._inflight = {"a": "работа-а", "b": "работа-b"}
shed = queue_d.deliver("live-c", lambda: {}, label="сверх очереди")
assert shed["verdict"] == SHED and "полна" in shed["reason"]

results["dispatch"] = {
    "done": done["verdict"],
    "retry_then_done_attempts": survived["attempts"],
    "redelivery_idempotent": retry_report["redelivered"] and calls["n"] == 3,
    "dlq_named": dead["verdict"] == DLQ,
    "timeout_verdict": timed["verdict"],
    "shed_verdict": shed["verdict"],
    "types_in_blood": sorted({e["type"] for e in journal.all()}),
}
journal.append(make(
    "act", "brainstem", "self", TRACE,
    {"act": "dispatch-live", "report": results["dispatch"],
     "method": "Dispatcher живьём: DONE, retry×3 → DONE, повтор ключа без эффекта (A01), DLQ поимённо, TIMEOUT с названным дедлайном, SHED без каскада; кровь — факты известными типами (A24/A25, SPEC-0001 п.10)"},
    Cost(0, 0, 0.0),
    path=[
        {"stage": "attempt-1", "verdict": "failed", "note": "канал дёрнулся (живой пример path, W-0020)"},
        {"stage": "retry", "verdict": "scheduled"},
        {"stage": "attempt-2", "verdict": "ok", "note": "доставка состоялась"},
    ],
))

# --- финал -----------------------------------------------------------------------
journal.append(make(
    "reflect", "brainstem", "self", TRACE,
    {
        "verdict": "ТЗ-2.4 dispatcher (A24, A25 СЛУЖЕНО), ТЗ-2.5 путь в крови (W-0020), ТЗ-3.1 честный ADR-0016 (локальный транспорт: stdio + localhost-http, наружный MCP HTTP+OAuth — за Человеком) служены замером",
        "honesty": "приёмка транспорта сначала честно красила дом (http-органы) — ADR написан по факту крови дома, а не по лозунгу «только stdio»",
        "next": "ТЗ-2.3 swarm-consent (A21), ТЗ-2.6 W-0028, ТЗ-3.2/3.3/3.4, донорский трек",
    },
    Cost(0, 0, 0.0),
    idempotency_key="wave29-reflect",
))

journal.close()
report = verify(JOURNAL)
print(json.dumps(report, ensure_ascii=False))
assert report["gaps"] == [] and not report.get("content_gaps")

rel = str(JOURNAL.relative_to(REPO_ROOT))
anchor = seal(JOURNAL, name=rel)
anchors_path = REPO_ROOT / "blood" / "anchors.jsonl"
existing = [json.loads(l) for l in anchors_path.read_text(encoding="utf-8").splitlines() if l.strip()]
if not any(r.get("file") == rel and r.get("last_sha256") == anchor["last_sha256"] for r in existing):
    with anchors_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(anchor, ensure_ascii=False) + "\n")
    print("якорь опечатан")
else:
    print("якорь того же состояния уже в книге")

print("ИТОГ ВОЛНЫ №29:", json.dumps(results, ensure_ascii=False, indent=2))
