# Живой прогон волны №23: правило тишины + бюджет внимания человека
# (W-0032 + W-0025, «одно другое не исключает»).
# Кровь волны пишется живым контуром (Loop/Gateway, pid1-контур одобрений,
# журнал v0.14.0), в конце опечатывается якорем в blood/anchors.jsonl.
# Пробы живьём:
# 1) необратимое без одобрения — veto до факта с заявленной ценой внимания
#    (P0, cost.attention=1), акт не исполнен;
# 2) запрос одобрения с окном → Человек одобрил → answer() = granted;
# 3) повторный план С одобрением — необратимое исполняется (новый трейс);
# 4) запрос с коротким окном, Человек молчит (реальный сон) — veto от
#    правила тишины, по умолчанию «нет», повторное решение — та же строка (A01);
# 5) опоздавшее одобрение после отмены — весть в крови, решение не переворачивает;
# 6) метрики внимания — read-only из крови (вопросы, прерывания, тишина,
#    ожидание, опасные действия рядом).
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import yaml  # noqa: E402

from blood.diary import render  # noqa: E402
from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, seal, verify  # noqa: E402
from brainstem import Budget, Loop, Step  # noqa: E402
from brainstem.approval import GRANTED, answer, grant, pending, request  # noqa: E402
from brainstem.attention import metrics, should_ask  # noqa: E402
from synapse.gateway import Gateway  # noqa: E402

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
ANCHORS = REPO_ROOT / "blood" / "anchors.jsonl"
BASE = "e98211a"  # 0.41.0 — база волны №23 (волна №22: обратимость и бюджет)

journal = Journal()
journal.attach(JOURNAL)

journal.append(make(
    event_type="boot",
    source="brainstem",
    organ="self",
    trace_id="wave23-silence-attention",
    payload={
        "role": "волна №23 — правило тишины (W-0032: окно и дефолт «нет») + бюджет внимания человека (W-0025: cost.attention, P0–P3)",
        "directive": "одно другое не исключает — ты полимат=мультиагент",
        "grain": "FR-09 пакета «Human Membrane» + дыра ревизии 2026-11-03 «нет правила для отсутствия PID 1»",
        "repo_base_commit": BASE,
    },
    cost=Cost(),
))

# --- Живые органы: stateful (t — необратимая по заявке запись) + senseless (эхо)
tmp = tempfile.mkdtemp(prefix="wave23-")
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

# --- Политика внимания на живых решениях (W-0025, should_ask) -----------------
policy_lines = []
for priority, safe in (("P0", False), ("P0", True), ("P1", False), ("P1", True), ("P2", False), ("P3", False)):
    ask_decision, why = should_ask(priority, safe_default=safe)
    policy_lines.append(f"- `{priority}` safe_default={str(safe).lower()} → {'СПРАШИВАЕМ' if ask_decision else 'не спрашиваем'}: {why}")

# --- Трейс 1: необратимое без одобрения — veto до факта, вопрос стоит денег ---
trace1 = "wave23-veto-p0"
done = loop.run(
    [Step(organ="stateful", tool="t", payload={"key": "прод", "value": "удалить"}, intent="удалить прод-таблицу", reversibility="irreversible")],
    trace_id=trace1,
    budget=Budget(),
)
assert done is False, "необратимое без одобрения не может пройти"
veto_events = [e for e in journal.by_trace(trace1) if e["type"] == "veto"]
assert veto_events and veto_events[0]["cost"].get("attention") == 1, "P0-вопрос обязан нести цену внимания"
acts_before = [e for e in journal.by_trace(trace1) if e["type"] == "act"]
assert not acts_before, "акта быть не должно — остановка до факта"
assert organ.state == {}, "орган не вызывался — эффект не случился"
print("трейс 1: veto до факта, cost.attention=1, орган не вызван")

# --- Трейс 2: запрос одобрения с окном → Человек одобрил → granted ------------
trace2 = "wave23-approval-granted"
ask = request(
    journal,
    what="удалить прод-таблицу (stateful.t)",
    window_seconds=3600,
    priority="P0",
    trace_id=trace2,
    organ="stateful",
    tool="t",
    question="Одобряешь необратимое удаление прод-таблицы? Окно тишины 1 час.",
)
assert ask["type"] == "approval.request" and ask["payload"]["priority"] == "P0"
verdict, _ = answer(journal, ask)
assert verdict == "waiting", "до одобрения и до истечения окна ответ — waiting"
give = grant(journal, ask, who="PID 1 (живой прогон волны №23)", trace_id=trace2, note="одобрено в кадре живого прогона")
verdict, given = answer(journal, ask)
assert verdict == GRANTED and given is not None and given["type"] == "approval.grant", "одобрение до окна не распознано"
assert given["causation_id"] == ask["id"], "одобрение обязано нести причинную связь на запрос"
print("трейс 2: approval.request → approval.grant → granted (causation_id честный)")

# --- Трейс 3: повторный план С одобрением — необратимое исполняется -----------
trace3 = "wave23-act-with-approval"
ok = loop.run(
    [Step(organ="stateful", tool="t", payload={"key": "прод", "value": "удалить"}, intent="удалить прод-таблицу (одобрено)", reversibility="irreversible", approval="PID 1, живой прогон волны №23")],
    trace_id=trace3,
    budget=Budget(),
)
assert ok is True, "необратимое с одобрением должно исполниться"
acts = [e for e in journal.by_trace(trace3) if e["type"] == "act"]
assert acts and acts[0]["payload"].get("reversibility") == "irreversible", "заявка класса едет с актом"
print("трейс 3: необратимое исполнено по одобрению (акт с заявленным классом)")

# --- Трейс 4: тишина за окном — veto от правила, по умолчанию «нет» -----------
trace4 = "wave23-silence-cancel"
silent_ask = request(
    journal,
    what="письмо наружу (упоминание дома в чужом issue)",
    window_seconds=1,
    priority="P1",
    trace_id=trace4,
    organ="senseless",
    question="Одобряешь письмо наружу? Окно тишины 1 секунда.",
)
time.sleep(1.2)  # живая тишина: реальное время идёт, Человек молчит
verdict, veto_env = answer(journal, silent_ask)
assert verdict == "cancelled_by_silence", "тишина за окном обязана отменить по-записанному"
assert veto_env is not None and veto_env["type"] == "veto" and veto_env["source"] == "pid1"
assert "тишины" in veto_env["payload"]["reason"], "отмена названа правилом, не подделана под Человека"
verdict2, same = answer(journal, silent_ask)
assert verdict2 == "cancelled_by_silence" and same["id"] == veto_env["id"], "повторное решение — та же строка (A01)"
vetoes_4 = [e for e in journal.by_trace(trace4) if e["type"] == "veto"]
assert len(vetoes_4) == 1, "вторая veto-строка запрещена (A01)"
print("трейс 4: тишина за окном → veto правила, повтор — та же строка (A01)")

# --- Трейс 5: опоздавшее одобрение — весть в крови, решение не переворачивает -
late = grant(journal, silent_ask, who="PID 1 (опоздал)", trace_id=trace4)
assert late["type"] == "approval.grant", "весть записана — кровь append-only"
verdict3, _ = answer(journal, silent_ask)
assert verdict3 == "cancelled_by_silence", "опоздавшее одобрение необратимое не оживляет"
left = pending(journal)
assert left == [], "без ответа и живого окна не осталось"
print("трейс 5: опоздавшее одобрение записано вестью, решение правила стоит")

# --- Метрики внимания (W-0025): read-only из крови ---------------------------
report = metrics(journal.all())
assert report["questions"] == 2, "два вопроса Человеку"
assert report["interruptions"] == 2, "оба вопроса — прерывания (P0/P1, attention=1)"
assert report["granted"] == 1 and report["cancelled_by_silence"] == 1 and report["refused"] == 0
assert report["dangerous_actions"] == 1, "рядом названо опасное действие — оборотную сторону не прячем"
assert report["wait_seconds_max"] is not None and report["wait_seconds_max"] >= 1.0, "живое ожидание тишины измерено"
print("метрики внимания:", {k: report[k] for k in ("questions", "interruptions", "granted", "cancelled_by_silence", "wait_seconds_max", "dangerous_actions")})

# --- Итог: дневник + метрики словами -----------------------------------------
summary = [
    "# Волна №23 — правило тишины и бюджет внимания (живой прогон)",
    "",
    f"База: `{BASE}` (0.41.0). Кровь: `blood.jsonl` — живой контур (Loop/Gateway, pid1-контур одобрений), журнал v0.14.0.",
    "",
    "## Политика внимания на живых решениях (W-0025)",
    "",
    *policy_lines,
    "",
    "## Метрики внимания (read-only из крови, неизмеримое = UNKNOWN)",
    "",
    f"- вопросов Человеку: {report['questions']} (прерываний: {report['interruptions']})",
    f"- одобрено: {report['granted']}; явных отказов: {report['refused']}; отменено тишиной: {report['cancelled_by_silence']}",
    f"- максимальное заявленное ожидание ответа: {report['wait_seconds_max']:.3f} с",
    f"- доля отказов среди решённых: {report['dismissed_fraction']}",
    f"- опасных (необратимых) действий рядом: {report['dangerous_actions']} — меньше вопросов не значит лучше, если растут опасные действия",
    "",
    "## Итог правила тишины (W-0032)",
    "",
    "- вопрос без окна не существует (fail-closed, ADR-0014);",
    "- одобрение до окна — granted, с честной причинной связью на запрос;",
    "- тишина за окном — veto от правила (по умолчанию «нет»), повтор — та же строка (A01);",
    "- опоздавшее одобрение — весть в крови, необратимое не оживляет;",
    "- ожидание не остановило дом: трейсы 1–5 идут один за другим.",
    "",
    "## Дневник прогона (read-проекция крови)",
    "",
    "```",
    render(journal, trace_id=None),
    "```",
    "",
]
(HERE / "output.md").write_text("\n".join(summary), encoding="utf-8")

# --- Печать крови якорем -----------------------------------------------------
seal(JOURNAL, name="wave23-silence-attention")
checked = verify(JOURNAL)
assert not checked["gaps"], "кровь прогона обязана быть целой"
print("кровь:", checked["events"], "конвертов, гэпов:", len(checked["gaps"]), "— опечатана якорем")
