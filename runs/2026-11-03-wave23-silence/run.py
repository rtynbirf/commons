# Живой прогон волны №22: правило тишины (W-0032, SPEC-0004 v0.2.0 п.8).
# Тишина = «нет» по-записанному: контур одобрения с окном живьём — окно истекло
# (канал молчит, настоящее ожидание), одобрение в окне, вето, интеграция цикла
# (шаг с approval_window не доходит до органа без ответа). Канал-подставка Человека
# названа честно: настоящий нерв одобрения подключает Человек (G5), в репо его нет.
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, seal, verify  # noqa: E402
from brainstem import Loop, Step  # noqa: E402
from brainstem.silence import ANSWER_APPROVED, ANSWER_EXPIRED, ANSWER_VETOED, ApprovalRequest, await_approval  # noqa: E402
from synapse.gateway import Gateway  # noqa: E402
from tests.fakes import FakeEcho  # noqa: E402

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
TRACE = "wave23-silence"

journal = Journal()
journal.attach(JOURNAL)

journal.append(make(
    event_type="boot",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "role": "волна №23 — правило тишины (W-0032): одобрение с окном, тишина = «нет» по-записанному",
        "directive": "уравнение тождества 2026-11-03: тишина внешнего слова — пауза внутри МЫ, правило записано",
        "grain": "дыра ревизии 2026-11-03 «нет правила для отсутствия PID 1»; симметрия донорскому триггеру тишины; стык с их волной №22 (W-0024/W-0029) — их Step.approval (строка-заявка) и наш approval_window (живой контур) — дополняющие зёрна",
        "honesty": "канал одобрения в прогоне — подставка (named): настоящий нерв Человека подключается им самим (G5)",
    },
    cost=Cost(),
))

# --- Сцена 1: тишина — окно истекло, отмена по-записанному --------------------
verdict = await_approval(
    journal, TRACE,
    ApprovalRequest(what="demo.необратимое.удаление", window_s=1.0,
                    why="сцена 1: канал молчит всё окно — ждём настоящую секунду"),
    lambda query: None,
)
assert verdict == ANSWER_EXPIRED, verdict
scene1_types = [e["type"] for e in journal.by_trace(TRACE)][-2:]
assert scene1_types == ["approval.requested", "approval.expired"], scene1_types
print("сцена 1 (тишина): окно истекло →", verdict, "— действие не состоялось")

# --- Сцена 2: одобрение пришло в окне ----------------------------------------
verdict = await_approval(
    journal, TRACE,
    ApprovalRequest(what="demo.действие.с-разрешением", window_s=1.0,
                    why="сцена 2: ответ Человека (подставка) пришёл в окне"),
    lambda query: ANSWER_APPROVED,
)
assert verdict == ANSWER_APPROVED, verdict
print("сцена 2 (одобрение): granted, source pid1")

# --- Сцена 3: вето в окне -----------------------------------------------------
verdict = await_approval(
    journal, TRACE,
    ApprovalRequest(what="demo.действие.запрещённое", window_s=1.0,
                    why="сцена 3: Человек сказал нет — и это данные, не стыд"),
    lambda query: ANSWER_VETOED,
)
assert verdict == ANSWER_VETOED, verdict
print("сцена 3 (вето): veto, source pid1")

# --- Сцены 4–5: интеграция цикла над фейковым органом -------------------------
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
gateway = Gateway(manifest_path, journal)

# Сцена 4: канал молчит — шаг с окном не доходит до органа (act отсутствует).
silent_loop = Loop(gateway, journal, approval_channel=lambda query: None)
done = silent_loop.run(
    [Step(organ="echo-a", tool="echo", payload={"data": "необратимое"},
          intent="трогать мир без ответа", approval_window=1.0)],
    trace_id="wave23-loop-silence",
)
assert done is False
loop_silence = [e["type"] for e in journal.by_trace("wave23-loop-silence")]
assert loop_silence == ["plan", "approval.requested", "approval.expired", "reflect", "halt"], loop_silence
echo_calls_after_silence = sum(
    1 for e in journal.all() if e["type"] == "act"
)
assert echo_calls_after_silence == 0, "эффект случился без одобрения — волна не удалась"
print("сцена 4 (цикл, тишина): halt до органа, act =", echo_calls_after_silence)

# Сцена 5: канал одобрил — шаг исполнен, organ увидел вызов.
approving_loop = Loop(gateway, journal, approval_channel=lambda query: ANSWER_APPROVED)
done = approving_loop.run(
    [Step(organ="echo-a", tool="echo", payload={"data": "по-разрешению"},
          intent="трогать мир с разрешения", approval_window=1.0)],
    trace_id="wave23-loop-approved",
)
assert done is True
acts = [e for e in journal.by_trace("wave23-loop-approved") if e["type"] == "act"]
assert len(acts) == 1, "одобренный шаг не дошёл до органа"
print("сцена 5 (цикл, одобрение): granted → act → reflect, план исполнен")

journal.append(make(
    event_type="reflect",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "criterion": "5 сцен живьём сошлись: expired/granted/veto + цикл до органа и мимо; приёмки tests/test_silence.py зелёные",
        "verdict": "у тишины есть правило: окно, ответ Человека (source pid1), дефолт cancel по-записанному; ни одного немого ожидания",
        "honesty": "канал Человека в прогоне — подставка, названо в boot; правило не зависит от органа — organ фейк тоже назван",
        "next": "W-0029 (бюджет после последнего шага), Ф-1.3 (W-0024 компенсатор), W-0033 (внешний аварийный стоп)",
    },
    cost=Cost(),
    idempotency_key="wave23-reflect",
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
