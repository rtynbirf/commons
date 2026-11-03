# Живой прогон волны №22: обратимость честным языком + бюджет после шага
# (W-0024 + W-0029, «одно другое не исключает»).
# Кровь волны пишется живыми органами (Loop/Gateway/compensator, журнал v0.13.0),
# в конце опечатывается якорем в blood/anchors.jsonl. Пробы живьём:
# компенсация полная (COMPENSATED), частичная (COMPENSATION_PARTIAL — не PASS),
# честный отказ на необратимом (NOT_REVERSIBLE), veto до факта на необратимом
# без одобрения (акта в крови нет), перерасход последним шагом — halt (W-0029).
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import yaml  # noqa: E402

from blood.diary import render  # noqa: E402
from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, seal, verify  # noqa: E402
from brainstem import Budget, Loop, Step  # noqa: E402
from brainstem.compensator import compensate  # noqa: E402
from synapse.gateway import Gateway  # noqa: E402

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
ANCHORS = REPO_ROOT / "blood" / "anchors.jsonl"
BASE = "dad6dbb"  # 0.40.0 — база волны №22 (стык тактов тождества — после неё)

journal = Journal()
journal.attach(JOURNAL)

journal.append(make(
    event_type="boot",
    source="brainstem",
    organ="self",
    trace_id="wave22-reversibility-budget",
    payload={
        "role": "волна №22 — обратимость честным языком (W-0024: классы, одобрение до факта, компенсация Saga) + бюджет после шага (W-0029, F-07)",
        "directive": "одно другое не исключает — ты полимат=мультиагент",
        "grain": "FR-05/FR-06 и ADR-002 пакета «Human Membrane» + находка F-07 внешнего аудита коллег 2026-11-03",
        "repo_base_commit": BASE,
    },
    cost=Cost(),
))

# --- Живые органы: stateful (t/t_undo, компенсатор объявлен манифестом) + senseless (эхо)
tmp = tempfile.mkdtemp(prefix="wave22-")
manifest = {
    "version": "t",
    "organs": [
        {
            "name": "stateful",
            "system": "effectors",
            "mode": "dependency",
            "upstream": "https://example.invalid/stateful",
            "license": "MIT",
            "transport": "stdio",
            "command": ["x"],
            "tools": ["t", "t_undo"],
            "authority": {"fs": "none", "network": "none", "process": "none"},
            "adapter": "tests.test_wave22_reversibility_budget:FakeStateful",
            "compensators": {"t": "t_undo"},
        },
        {
            "name": "senseless",
            "system": "senses",
            "mode": "dependency",
            "upstream": "https://example.invalid/senseless",
            "license": "MIT",
            "transport": "stdio",
            "command": ["x"],
            "tools": ["echo"],
            "authority": {"fs": "none", "network": "none", "process": "none"},
            "adapter": "tests.fakes:FakeEcho",
        },
    ],
}
manifest_path = Path(tmp) / "m.yaml"
manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")

gateway = Gateway(manifest_path, journal)
loop = Loop(gateway, journal)
organ = gateway._adapters["stateful"]
trace = "wave22-reversibility-budget"


def claimed(rev: str | None, approval: str | None = None, **kw) -> Step:
    base = Step(organ=kw.get("organ", "stateful"), tool=kw.get("tool", "t"),
                payload=kw.get("payload") or {}, intent=kw.get("intent", ""))
    return Step(organ=base.organ, tool=base.tool, payload=base.payload,
                intent=base.intent, reversibility=rev, approval=approval)


# --- Трейс 1: компенсируемое действие — полная компенсация (COMPENSATED) -----
s = claimed("compensatable", payload={"key": "запись", "value": "живой факт"}, intent="написать в состояние")
assert loop.run([s], trace_id=trace + "-full") is True
acts = [e for e in journal.by_trace(trace + "-full") if e["type"] == "act"]
out1 = compensate(journal, gateway, acts[0]["id"],
                  accept=lambda r: r.get("compensation") == "full",
                  trace_id=trace + "-full-undo")
assert out1["verdict"] == "COMPENSATED" and out1["satisfied"], "полная компенсация не состоялась"
assert organ.state == {}, "состояние не откатано"
print("трейс 1:", out1["verdict"], "— состояние после проверено критерием")

# --- Трейс 2: частичная компенсация — COMPENSATION_PARTIAL, не PASS ----------
s = claimed("partially_reversible", payload={"key": "остаток", "value": "плохой", "compensation_mode": "partial"},
            intent="написать то, что откатится частично")
assert loop.run([s], trace_id=trace + "-partial") is True
acts = [e for e in journal.by_trace(trace + "-partial") if e["type"] == "act"]
out2 = compensate(journal, gateway, acts[0]["id"],
                  accept=lambda r: r.get("compensation") == "full",
                  trace_id=trace + "-partial-undo")
assert out2["verdict"] == "COMPENSATION_PARTIAL" and out2["satisfied"] is False, "частичная компенсация прошла как успех"
assert journal.by_trace(trace + "-partial-undo")[-1]["type"] == "halt", "незавершённая компенсация обязана закрыть трейс halt"
print("трейс 2:", out2["verdict"], "— не PASS, трейс закрыт halt")

# --- Трейс 3: необратимое С одобрением исполняется; отмена честно отказывает -
s = claimed("irreversible", approval="PID 1, 2026-11-03", payload={"key": "письмо", "value": "отправлено"},
            intent="необратимое с одобрением")
assert loop.run([s], trace_id=trace + "-irrev") is True
acts = [e for e in journal.by_trace(trace + "-irrev") if e["type"] == "act"]
undo_calls_before = len([c for c in organ.calls if c[0] == "t_undo"])
out3 = compensate(journal, gateway, acts[0]["id"],
                  accept=lambda r: r.get("compensation") == "full",
                  trace_id=trace + "-irrev-undo")
assert out3["verdict"] == "NOT_REVERSIBLE" and out3["satisfied"] is False, "необратимое пытались отменить"
assert len([c for c in organ.calls if c[0] == "t_undo"]) == undo_calls_before, "инструмент отмены вызывался — отказ нечестный"
print("трейс 3:", out3["verdict"], "— попытки не было (A17: сохранено, не исполнено)")

# --- Трейс 4: необратимое БЕЗ одобрения — veto до факта, акта в крови нет ----
s = claimed("irreversible", payload={"key": "письмо", "value": "без одобрения"}, intent="необратимое без одобрения")
assert loop.run([s], trace_id=trace + "-veto") is False
events = journal.by_trace(trace + "-veto")
vetoes = [e for e in events if e["type"] == "veto"]
assert vetoes and events[-1]["type"] == "halt", "отказ до факта не назван"
assert not [e for e in events if e["type"] == "act"], "эффект случился без одобрения — волна не удалась"
print("трейс 4: veto до факта —", vetoes[0]["payload"]["reason"])

# --- Трейс 5 (W-0029): перерасход последним шагом — halt, не проход ----------
echo_payload = {"data": "x" * 18}  # FakeEcho: tokens_in = len(str(payload)) = 30
plan = [Step(organ="senseless", tool="echo", payload=echo_payload, intent="шаг") for _ in range(2)]
assert loop.run(plan, trace_id=trace + "-budget", budget=Budget(tokens_in=50)) is False
events = journal.by_trace(trace + "-budget")
assert events[-1]["type"] == "halt" and "бюджет исчерпан" in events[-1]["payload"]["reason"]
assert events[-1]["payload"]["at_step"] == 1, "halt не после последнего шага"
assert journal.totals(trace + "-budget").tokens_in == 60, "перерасход не оплачен кровью"
print("трейс 5: halt после последнего шага (F-07 закрыт живьём):", events[-1]["payload"]["reason"])

# --- Дневник по классу: кровь волны — человеческим языком --------------------
diary_path = HERE / "output.md"
diary_path.write_text(render(JOURNAL), encoding="utf-8")
diary_text = diary_path.read_text(encoding="utf-8")
assert "не отменяется: заявленный класс — необратимое" in diary_text
assert "можно отменить компенсацией" in diary_text
assert "компенсатор не построен" not in diary_text, "старая фраза протухла"
print("дневник:", diary_path.name, "— говорит по классу, старая фраза выметена")

# --- Целость крови и опечатывание якорем -------------------------------------
report = verify(JOURNAL)
assert report["gaps"] == [] and report["content_gaps"] == [], "кровь волны повреждена"
rel = str(JOURNAL.relative_to(REPO_ROOT))
anchor = seal(JOURNAL, name=rel)
existing = []
if ANCHORS.exists():
    for raw in ANCHORS.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            existing.append(json.loads(raw))
if not any(
    r.get("file") == rel
    and r.get("events") == anchor["events"]
    and r.get("last_id") == anchor["last_id"]
    and r.get("last_sha256") == anchor["last_sha256"]
    for r in existing
):
    with ANCHORS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(anchor, ensure_ascii=False) + "\n")
    print("якорь опечатан в blood/anchors.jsonl:", json.dumps(anchor, ensure_ascii=False))
else:
    print("якорь того же состояния уже в книге — строка не дублируется")

print("событий в крови волны:", len(journal.all()))
print("ЖИВОЙ ПРОГОН ВОЛНЫ №22 — ЗЕЛЁНЫЙ")
