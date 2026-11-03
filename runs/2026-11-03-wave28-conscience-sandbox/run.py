# Живой прогон волны №28 (Ф-2 органы-функции, docs/TZ.md ТЗ-2.1, ТЗ-2.2).
# Дата: 2026-11-03. Красный прогон приёмок: сборка падает на нетронутом коде
# (brainstem.sandbox и blood.conscience не существуют) — зафиксирован до фикса.
# Пробы живьём: совесть на ложной посылке (не поддакивает) и на верной
# (согласие с доказательством) — ТЗ-2.1/A19; гипотеза в крови unverified,
# шаг на гипотезе без критерия — veto до факта, шаг с критерием — исполнен —
# ТЗ-2.2/A20.
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.conscience import calibrate  # noqa: E402
from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, seal, verify  # noqa: E402
from brainstem.loop import Loop, Step  # noqa: E402
from brainstem.sandbox import SANDBOX_NOTE, Sandbox  # noqa: E402
from synapse.gateway import Gateway  # noqa: E402

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
TRACE = "wave28-conscience-sandbox"
SANDBOX_TRACE = "wave28-sandbox-live"

if JOURNAL.exists():
    JOURNAL.unlink()  # повторный прогон пишет кровь заново

journal = Journal()
journal.attach(JOURNAL)
results: dict[str, dict] = {}

# --- ТЗ-2.1 / A19: совесть живьём ---------------------------------------------
journal.append(make("error", "brainstem", "self", "tr-live-a", {"reason": "канал упал"}, Cost(0, 0, 0.0)))
journal.append(make("halt", "brainstem", "self", "tr-live-b", {"reason": "бюджет исчерпан"}, Cost(0, 0, 0.0)))

false_premise = calibrate({"refusals": 0}, journal)
assert false_premise["agree"] is False and false_premise["disagreements"]
true_premise = calibrate({"refusals": 2, "refusal_types": ["error", "halt"]}, journal)
assert true_premise["agree"] is True and true_premise["disagreements"] == []
try:
    calibrate({"настроение": "хорошее"}, journal)
    raise AssertionError("чужой ключ посылки обязан роняться")
except ValueError:
    pass
results["conscience"] = {
    "false_premise_agree": false_premise["agree"],
    "false_premise_words": false_premise["words"],
    "true_premise_agree": true_premise["agree"],
    "true_premise_words": true_premise["words"],
    "grammar_fail_closed": True,
}
journal.append(make(
    "act", "brainstem", "self", TRACE,
    {"act": "conscience-live", "report": results["conscience"],
     "method": "calibrate(): ложная посылка «отказов не было» — Не согласен с поимённым расхождением; верная — Согласен с доказательством; чужой ключ — ValueError (A19, SPEC-0003 п.20)"},
    Cost(0, 0, 0.0),
))

# --- ТЗ-2.2 / A20: песочница живьём --------------------------------------------
tmp = Path(tempfile.mkdtemp(prefix="wave28-sandbox-"))
try:
    manifest = {
        "version": "0.1.0",
        "updated": "2026-11-03",
        "transport_default": "stdio",
        "organs": [{
            "name": "creator",
            "system": "cognition",
            "mode": "dependency",
            "upstream": "https://example.invalid/creator",
            "license": "MIT",
            "transport": "stdio",
            "command": "fake-creator",
            "healthcheck": "initialize handshake",
            "tools": ["write"],
            "authority": {"fs": {"mode": "read-only", "paths": [str(tmp)]}, "network": "none", "process": "none"},
            "adapter": "tests.fakes:FakeEcho",
        }],
    }
    import yaml

    manifest_path = tmp / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    gw = Gateway(manifest_path, journal=journal)
    sandbox = Sandbox(journal)
    hyp = sandbox.propose("если резюмировать кровь окном недели, запахи виднее")
    assert hyp["trust"] == "unverified" and hyp["payload"]["sandbox"] is True
    assert SANDBOX_NOTE in json.dumps(hyp, ensure_ascii=False)

    loop = Loop(gw, journal)
    # гипотеза без критерия — veto до факта
    vetoed = loop.run(
        [Step(organ="creator", tool="write", intent="запись по гипотезе",
              payload={"on_hypothesis": True}, basis=hyp["id"])],
        trace_id=SANDBOX_TRACE,
    )
    assert vetoed is False
    acts_after_veto = [e for e in journal.all() if e["type"] == "act" and e["trace_id"] == SANDBOX_TRACE]
    assert acts_after_veto == []
    vetoes = [e for e in journal.all() if e["type"] == "veto" and e["trace_id"] == SANDBOX_TRACE]

    # гипотеза с критерием — проверенный путь
    executed = loop.run(
        [Step(organ="creator", tool="write", intent="запись по гипотезе",
              payload={"on_hypothesis": True}, basis=hyp["id"],
              accept={"type": "object"}, reversibility="reversible")],
        trace_id=SANDBOX_TRACE,
    )
    assert executed is True
    acts = [e for e in journal.all() if e["type"] == "act" and e["trace_id"] == SANDBOX_TRACE]
    plans = [e for e in journal.all() if e["type"] == "plan" and e["trace_id"] == SANDBOX_TRACE]
    assert acts and plans[-1]["payload"]["basis"] == hyp["id"]
    results["sandbox"] = {
        "hypothesis_trust": hyp["trust"],
        "veto_reason": vetoes[-1]["payload"]["reason"] if vetoes else None,
        "vetoed_run": vetoed,
        "verified_run": executed,
        "plan_carries_basis": plans[-1]["payload"].get("basis"),
        "acts_after_veto": 0,
        "acts_after_verify": len(acts),
    }
    journal.append(make(
        "act", "brainstem", "self", TRACE,
        {"act": "sandbox-live", "report": results["sandbox"],
         "method": "Гипотеза unverified в крови; шаг на ней без Step.accept — veto до факта (акта нет); с критерием — исполнен, план несёт basis (A20, SPEC-0001 п.9)"},
        Cost(0, 0, 0.0),
        idempotency_key="wave28-sandbox-act",
    ))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# --- финал -----------------------------------------------------------------------
journal.append(make(
    "reflect", "brainstem", "self", TRACE,
    {
        "verdict": "ТЗ-2.1 совесть (A19) и ТЗ-2.2 творческая песочница (A20) служены замером: совесть на ложной посылке не поддакивает (расхождение поимённо), гипотеза не становится фактом без проверки (veto до факта)",
        "honesty": "красный прогон зафиксирован на нетронутом коде (сборка без blood.conscience/brainstem.sandbox падает)",
        "next": "ТЗ-2.3 swarm-consent (A21), ТЗ-2.4 dispatcher (A24/A25), ТЗ-2.5 W-0020, ТЗ-2.6 W-0028, Ф-3",
    },
    Cost(0, 0, 0.0),
    idempotency_key="wave28-reflect",
))

journal.close()

report = verify(JOURNAL)
print(json.dumps(report, ensure_ascii=False, indent=2))
assert report["gaps"] == [] and not report.get("content_gaps")

rel = str(JOURNAL.relative_to(REPO_ROOT))
anchor = seal(JOURNAL, name=rel)
anchors_path = REPO_ROOT / "blood" / "anchors.jsonl"
existing = [json.loads(l) for l in anchors_path.read_text(encoding="utf-8").splitlines() if l.strip()]
if not any(
    r.get("file") == rel and r.get("events") == anchor["events"]
    and r.get("last_sha256") == anchor["last_sha256"] for r in existing
):
    with anchors_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(anchor, ensure_ascii=False) + "\n")
    print("якорь опечатан:", json.dumps(anchor, ensure_ascii=False))
else:
    print("якорь того же состояния уже в книге")

print("ИТОГ ВОЛНЫ №28:", json.dumps(results, ensure_ascii=False, indent=2))
