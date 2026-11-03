# Живой прогон стыка волн №23 (0.42.1): их контур тишины — база, зерно цены
# нашей линии (W-0025) вжито в контур. Сцены: тишина за окном (настоящая секунда),
# одобрение, вето, цикл до органа и мимо; цена P0-вопроса — в крови; метрики и
# дневник читают кровь стыка. Канал-подставка Человека названа честно: настоящий
# нерв одобрения подключает Человек (G5), в репо его нет.
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.diary import entries, render  # noqa: E402
from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, seal, verify  # noqa: E402
from brainstem import Loop, Step  # noqa: E402
from brainstem.attention import metrics  # noqa: E402
from brainstem.silence import ANSWER_APPROVED, ANSWER_EXPIRED, ANSWER_VETOED, ApprovalRequest, await_approval  # noqa: E402
from synapse.gateway import Gateway  # noqa: E402
from tests.fakes import FakeEcho  # noqa: E402

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
TRACE = "wave23-junction"

journal = Journal()
journal.attach(JOURNAL)

journal.append(make(
    event_type="boot",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "role": "стык волн №23 (0.42.1): их контур тишины — база, параллельная машина крови выметена, зерно цены вжито",
        "directive": "одно другое не исключает: W-0032 живёт контуром brainstem/silence.py, зерно W-0025 (цена вопроса) — в контуре",
        "junction": "дисциплина стыка волны №18: их база целиком, наш дубликат выметен, кровь нашей линии — вещественное доказательство (runs/2026-11-03-wave23-silence-attention)",
        "honesty": "канал одобрения в прогоне — подставка (named): настоящий нерв Человека подключается им самим (G5)",
    },
    cost=Cost(),
))

# --- Сцена 1: тишина за окном — вопрос о необратимом несёт цену P0 ------------
verdict = await_approval(
    journal, "wave23-junction-silence",
    ApprovalRequest(what="demo.необратимое.без-ответа", window_s=1.0,
                    why="сцена 1: канал молчит всю настоящую секунду — тишина = «нет»",
                    priority="P0"),
    lambda query: None,
    clock=time.monotonic,  # настоящая секунда ожидания, как у их линии
)
assert verdict == ANSWER_EXPIRED, verdict
silence_events = [e for e in journal.by_trace("wave23-junction-silence")]
assert [e["type"] for e in silence_events] == ["approval.requested", "approval.expired"], silence_events
asked = silence_events[0]
assert asked["cost"].get("attention") == 1, asked["cost"]  # зерно стыка: P0-вопрос несёт цену
print("сцена 1 (тишина): expired по-записанному; approval.requested несёт cost.attention=1 (P0)")

# --- Сцена 2: одобрение в окне ------------------------------------------------
verdict = await_approval(
    journal, "wave23-junction-approved",
    ApprovalRequest(what="demo.необратимое.с-разрешением", window_s=1.0,
                    why="сцена 2: ответ Человека (подставка) пришёл в окне",
                    priority="P0"),
    lambda query: ANSWER_APPROVED,
)
assert verdict == ANSWER_APPROVED, verdict
print("сцена 2 (одобрение): granted, source pid1")

# --- Сцена 3: вето в окне ------------------------------------------------------
verdict = await_approval(
    journal, "wave23-junction-veto",
    ApprovalRequest(what="demo.необратимое.запрещённое", window_s=1.0,
                    why="сцена 3: Человек сказал нет — и это данные, не стыд",
                    priority="P0"),
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

# Сцена 4: канал молчит — шаг с окном не доходит до органа (act отсутствует);
# вопрос контура о необратимом — P0-цена (зерно стыка в цикле).
silent_house = Loop(gateway, journal, approval_channel=lambda query: None)
done = silent_house.run(
    [Step(organ="echo-a", tool="echo", payload={"data": "необратимое"},
          intent="трогать мир без ответа", reversibility="irreversible", approval_window=1.0)],
    trace_id="wave23-junction-loop-silence",
)
assert done is False
loop_silence = [e["type"] for e in journal.by_trace("wave23-junction-loop-silence")]
assert loop_silence == ["plan", "approval.requested", "approval.expired", "reflect", "halt"], loop_silence
requested = [e for e in journal.by_trace("wave23-junction-loop-silence") if e["type"] == "approval.requested"][0]
assert requested["cost"].get("attention") == 1, requested["cost"]
assert sum(1 for e in journal.all() if e["type"] == "act") == 0, "эффект случился без одобрения"
print("сцена 4 (цикл, тишина): halt до органа, act = 0, вопрос — P0-цена в крови")

# Сцена 5: канал одобрил — необратимый шаг исполнен, акт несёт класс обратимости.
approving_house = Loop(gateway, journal, approval_channel=lambda query: ANSWER_APPROVED)
done = approving_house.run(
    [Step(organ="echo-a", tool="echo", payload={"data": "по-разрешению"},
          intent="трогать мир с разрешения", reversibility="irreversible", approval_window=1.0)],
    trace_id="wave23-junction-loop-approved",
)
assert done is True
acts = [e for e in journal.by_trace("wave23-junction-loop-approved") if e["type"] == "act"]
assert len(acts) == 1 and acts[0]["payload"].get("reversibility") == "irreversible"
print("сцена 5 (цикл, одобрение): granted → act → reflect, план исполнен")

# --- Чтение своей крови: метрики внимания и дневник на крови стыка ------------
report = metrics(journal.all())
assert report["questions"] == 5, report  # 3 контурных вопроса + 2 вопроса цикла
assert report["interruptions"] == 5, report  # все о необратимом — P0, цена заявлена (зерно стыка)
assert report["granted"] == 2, report
assert report["refused"] == 1, report
assert report["cancelled_by_silence"] == 2, report
assert report["dangerous_actions"] == 1, report
print("метрики стыка:", json.dumps(report, ensure_ascii=False))

diary_report = entries(journal)
rendered = render(journal)
(HERE / "output.md").write_text(rendered, encoding="utf-8")
diary_results = [record["результат"] for record in diary_report["records"]]
assert any("вопрос Человеку" in r for r in diary_results), diary_results[:6]
assert any("тишина" in r for r in diary_results), diary_results[:6]
print("дневник стыка: кровь прочитана на обоих диалектах — output.md записан")

journal.append(make(
    event_type="reflect",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "criterion": "5 сцен живьём: тишина/одобрение/вето контуром + цикл до органа и мимо; цена P0-вопроса в крови; метрики и дневник читают кровь стыка",
        "verdict": "одно другое не исключает: контур их линии — машина правила, зерно нашей линии — цена вопроса; параллельная машина выметена, кровь обеих линий читается домом",
        "honesty": "канал Человека в прогоне — подставка, названо в boot; орган — фейк, названо",
        "next": "W-0033 (внешний аварийный стоп петли), W-0030 (гейт «поведение без спеки» в doctor)",
    },
    cost=Cost(),
    idempotency_key="wave23-junction-reflect",
))

journal.close()

verify_report = verify(JOURNAL)
print(json.dumps(verify_report, ensure_ascii=False, indent=2))
assert verify_report["gaps"] == [], "цепочка порядка порвана"
assert not verify_report.get("content_gaps"), "подмена в собственной крови"

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
