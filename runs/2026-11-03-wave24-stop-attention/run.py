# Живой прогон волны №24: внешний аварийный стоп (W-0033) + бюджет внимания (W-0025).
# Стоп подаётся снаружи между шагами честным контуром stop.requested (source pid1)
# → reflect → halt; внимание считается в крови по фактам (cost.attention + P0).
# Канал одобрения и рука, кладущая стоп-файл, — подставки, названные в boot:
# настоящий нерв Человека подключает сам Человек (G5), в репо его нет.
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, seal, verify  # noqa: E402
from brainstem import Budget, Loop, Step  # noqa: E402
from brainstem.silence import ANSWER_APPROVED  # noqa: E402
from brainstem.stop import FileStopSignal  # noqa: E402
from synapse.gateway import Gateway  # noqa: E402
from tests.fakes import FakeEcho  # noqa: E402

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
TRACE = "wave24-stop-attention"

journal = Journal()
journal.attach(JOURNAL)

journal.append(make(
    event_type="boot",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "role": "волна №24 — внешний аварийный стоп (W-0033) и бюджет внимания (W-0025)",
        "grain": "дыра ревизии 2026-11-03 «аварийный останов петли» + зерно FR-09 пакета «Human Membrane»",
        "honesty": "канал одобрения и рука, кладущая стоп-файл, — подставки (named): настоящий нерв Человека подключает сам Человек (G5); стоп-файл — текст как универсальный нерв (SPEC-0010)",
    },
    cost=Cost(),
))

manifest = {
    "version": "run-0.1.0",
    "updated": "2026-11-03",
    "transport_default": "stdio",
    "organs": [{
        "name": "echo-a",
        "system": "senses",
        "mode": "dependency",
        "upstream": "https://example.invalid/echo-a",
        "license": "MIT",
        "transport": "stdio",
        "command": "fake-echo",
        "healthcheck": "initialize handshake",
        "tools": ["echo"],
        "authority": {"fs": "read-only", "network": "none"},
        "adapter": "tests.fakes:FakeEcho",
    }],
}
manifest_path = HERE / "manifest-run.yaml"
manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")

# --- Сцена 1: стоп-файл стоит до старта — первый шаг не исполняется ------------
stop1 = HERE / "stop-1.txt"
stop1.write_text("хватит на сегодня", encoding="utf-8")
loop1 = Loop(Gateway(manifest_path, journal), journal, stop_check=FileStopSignal(stop1))
done = loop1.run(
    [Step(organ="echo-a", tool="echo", payload={"data": "не начнётся"}, intent="шаг, которого не будет")],
    trace_id="wave24-scene1-stopfile",
)
assert done is False
kinds = [e["type"] for e in journal.by_trace("wave24-scene1-stopfile")]
assert kinds == ["stop.requested", "reflect", "halt"], kinds
stop = journal.by_trace("wave24-scene1-stopfile")[0]
assert stop["source"] == "pid1" and stop["cost"]["attention"] == 1 and stop["attention_class"] == "P0"
assert not [e for e in journal.by_trace("wave24-scene1-stopfile") if e["type"] == "act"]
print("сцена 1 (стоп до старта): stop.requested (pid1, P0) → halt, act = 0")

# --- Сцена 2: стоп между шагами — первый шаг договаривает, второй не начат -----
stop2 = HERE / "stop-2.txt"

def human_stand_in(query: dict) -> str:
    # подстава, названная в boot: одобрив, Человек тут же кладёт стоп — дальше не надо
    stop2.write_text("одобрил и остановил — дальше не надо", encoding="utf-8")
    return ANSWER_APPROVED

loop2 = Loop(Gateway(manifest_path, journal), journal, stop_check=FileStopSignal(stop2), approval_channel=human_stand_in)
done = loop2.run(
    [
        Step(organ="echo-a", tool="echo", payload={"data": "первый"}, intent="одобряемый шаг", approval_window=0.2, approval_why="живой вопрос, после которого Человек кладёт стоп"),
        Step(organ="echo-a", tool="echo", payload={"data": "второй"}, intent="шаг, до которого не дойдёт"),
    ],
    trace_id="wave24-scene2-boundary",
)
assert done is False
kinds = [e["type"] for e in journal.by_trace("wave24-scene2-boundary")]
assert kinds == [
    "plan", "approval.requested", "approval.granted", "act", "observe", "reflect",
    "stop.requested", "reflect", "halt",
], kinds
assert "одобрил и остановил" in journal.by_trace("wave24-scene2-boundary")[-1]["payload"]["reason"]
print("сцена 2 (стоп между шагами): первый шаг полон, второй не планировался")

# --- Сцена 3: стоп во время живого вызова — орган договаривает, трейс закрыт на границе ----
stop3 = HERE / "stop-3.txt"
manifest["organs"].append({
    "name": "slow-a",
    "system": "senses",
    "mode": "dependency",
    "upstream": "https://example.invalid/slow-a",
    "license": "MIT",
    "transport": "stdio",
    "command": "fake-slow",
    "healthcheck": "initialize handshake",
    "tools": ["echo"],
    "authority": {"fs": "read-only", "network": "none"},
    "adapter": "tests.fakes:SlowEcho",
    "delay": 0.3,
})
manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
# Рука Человека — вне тела (подстава, названная в boot): сценарий кладёт стоп-файл
# в середине живого вызова; орган полномочий не нарушает и договаривает.
timer = threading.Timer(0.12, lambda: stop3.write_text("хватит, орган доработает", encoding="utf-8"))
timer.start()
loop3 = Loop(Gateway(manifest_path, journal), journal, stop_check=FileStopSignal(stop3))
done = loop3.run(
    [Step(organ="slow-a", tool="echo", payload={"data": "живой вызов"}, intent="орган живёт треть секунды, стоп кладётся во время")],
    trace_id="wave24-scene3-organ-finishes",
)
assert done is False
events3 = journal.by_trace("wave24-scene3-organ-finishes")
kinds = [e["type"] for e in events3]
assert kinds == ["plan", "act", "observe", "reflect", "stop.requested", "reflect", "halt"], kinds
assert stop3.exists()
assert "хватит, орган доработает" in events3[-1]["payload"]["reason"]
print("сцена 3 (стоп во время вызова): орган договаривает, трейс закрыт на его границе")

# --- Сцена 4: вопрос с окном — внимание в крови по фактам -----------------------
loop4 = Loop(Gateway(manifest_path, journal), journal, approval_channel=lambda q: ANSWER_APPROVED)
done = loop4.run(
    [Step(organ="echo-a", tool="echo", payload={"data": "по разрешению"}, intent="вопрос с окном", approval_window=0.2, approval_why="живой замер внимания")],
    trace_id="wave24-scene4-attention-asked",
)
assert done is True
asked = [e for e in journal.by_trace("wave24-scene4-attention-asked") if e["type"] == "approval.requested"][0]
assert asked["cost"]["attention"] == 1 and asked["attention_class"] == "P0"
totals4 = journal.totals("wave24-scene4-attention-asked")
assert totals4.attention == 1, totals4
print("сцена 4 (вопрос с окном): cost.attention = 1, P0; totals трейса видят внимание")

# --- Сцена 5: бюджет внимания исчерпан — второй вопрос не задаётся --------------
loop5 = Loop(Gateway(manifest_path, journal), journal, approval_channel=lambda q: ANSWER_APPROVED)
done = loop5.run(
    [
        Step(organ="echo-a", tool="echo", payload={"data": "вопрос 1"}, intent="первый вопрос", approval_window=0.2),
        Step(organ="echo-a", tool="echo", payload={"data": "вопрос 2"}, intent="косметический вопрос, которого не будет", approval_window=0.2),
    ],
    trace_id="wave24-scene5-attention-budget",
    budget=Budget(attention=1),
)
assert done is False
asked5 = [e for e in journal.by_trace("wave24-scene5-attention-budget") if e["type"] == "approval.requested"]
assert len(asked5) == 1, "второй вопрос был задан при исчерпанном бюджете внимания"
halt5 = [e for e in journal.by_trace("wave24-scene5-attention-budget") if e["type"] == "halt"][-1]
assert "attention" in halt5["payload"]["reason"]
print("сцена 5 (бюджет внимания): исчерпание — halt до следующего вопроса, косметики нет")

journal.append(make(
    event_type="reflect",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "criterion": "5 сцен живьём сошлись: стоп до старта, стоп между шагами, стоп во время живого вызова (орган договаривает), внимание вопроса в крови, бюджет внимания останавливает до следующего вопроса; приёмки tests/test_wave24_stop_attention.py зелёные",
        "verdict": "трейс останавливается по слову Человека честным контуром stop.requested → reflect → halt (воля — source pid1); внимание Человека — четвёртый ресурс бюджета: счёт по фактам, косметических вопросов нет",
        "honesty": "канал одобрения и стоп-рука — подставки, названо в boot; орган сцен 1–2, 4–5 — фейк FakeEcho (предмет прогона — контур, не орган); SlowEcho в сцене 3 — тоже подстава (кладёт стоп во время вызова)",
        "next": "W-0034 (гейт дрейфа аксиом в doctor), W-0035 (линзы по самому дому), W-0036 (матрица приоритета законов)",
    },
    cost=Cost(),
    idempotency_key="wave24-reflect",
))

journal.close()

report = verify(JOURNAL)
print(json.dumps(report, ensure_ascii=False, indent=2))
assert report["gaps"] == [], "цепочка порядка порвана"
assert not report.get("content_gaps"), "подмена в собственной крови"

# --- Якорь: опечатываем кровь прогона в якорную книгу (append-only, дедуп) ----
rel = str(JOURNAL.relative_to(REPO_ROOT))
anchor = seal(JOURNAL, name=rel)
anchors_path = REPO_ROOT / "blood" / "anchors.jsonl"
existing = []
if anchors_path.exists():
    for raw in anchors_path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            existing.append(json.loads(raw))
if not any(
    r.get("file") == rel
    and r.get("events") == anchor["events"]
    and r.get("last_id") == anchor["last_id"]
    and r.get("last_sha256") == anchor["last_sha256"]
    for r in existing
):
    with anchors_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(anchor, ensure_ascii=False) + "\n")
    print("якорь опечатан в blood/anchors.jsonl:", json.dumps(anchor, ensure_ascii=False))
else:
    print("якорь того же состояния уже в книге — строка не дублируется")
