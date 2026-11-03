# Живой прогон волны №24 (0.43.0): внешний аварийный стоп петли (W-0033,
# SPEC-0001 v0.6.0 п.8) и гейт «поведение без спеки» (W-0030). Сцены:
# стоп до первого шага, стоп между шагами (сделанное не вычёркивается),
# молчащий сигнал (трейс живёт), упавший сигнал (fail-closed), файловый
# нерв живого хоста (читает причину, потребляет файл), живая проба
# spec-drift гейта. Каналы — подставки (named): настоящий нерв Человека
# подключает Человек (G5); орган — фейк FakeEcho (named).
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.diary import entries, render  # noqa: E402
from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, seal, verify  # noqa: E402
from brainstem import Loop, Step  # noqa: E402
from brainstem.stop import file_stop_signal  # noqa: E402
from synapse.gateway import Gateway  # noqa: E402
from tests.fakes import FakeEcho  # noqa: E402

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
TRACE = "wave24-stop-drift"

journal = Journal()
journal.attach(JOURNAL)

journal.append(make(
    event_type="boot",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "role": "волна №24 (0.43.0): внешний аварийный стоп петли (W-0033, SPEC-0001 v0.6.0 п.8) + гейт «поведение без спеки» (W-0030)",
        "directive": "одно другое не исключает: стоп-кран — нерв цикла, spec-drift — машина принципа «спека раньше кода»",
        "honesty": "стоп-сигнал и канал одобрения в прогоне — подставки (named): настоящий нерв Человека подключается им самим (G5); орган — фейк FakeEcho (named)",
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
gateway = Gateway(manifest_path, journal)

# --- Сцена 1: стоп-кран нажат до старта — ни одного акта ----------------------
crashed_house = Loop(gateway, journal, stop_signal=lambda: "авария до старта")
done = crashed_house.run(
    [Step(organ="echo-a", tool="echo", payload={"data": "s1"}, intent="шаг, которого не будет")],
    trace_id="wave24-scene1-stop-before-start",
)
assert done is False
s1 = [e["type"] for e in journal.by_trace("wave24-scene1-stop-before-start")]
assert s1 == ["halt"], s1  # стоп до старта: плана не было — только halt (граница перед первым шагом)
halt1 = [e for e in journal.by_trace("wave24-scene1-stop-before-start") if e["type"] == "halt"][0]
assert halt1["payload"]["source"] == "external", halt1["payload"]
assert halt1["payload"]["at_step"] == 0
print("сцена 1 (стоп до старта): halt source=external at_step=0 — плана не было, act = 0")

# --- Сцена 2: стоп между шагами — шаг 0 оплачен, шаг 1 не начался -------------


def spy_signal() -> str | None:
    reflects = sum(1 for e in journal.by_trace("wave24-scene2-stop-between") if e["type"] == "reflect")
    return "Человек нажал стоп-кран" if reflects >= 1 else None


between_house = Loop(gateway, journal, stop_signal=spy_signal)
done = between_house.run(
    [
        Step(organ="echo-a", tool="echo", payload={"data": "шаг-0"}, intent="шаг до стопа"),
        Step(organ="echo-a", tool="echo", payload={"data": "шаг-1"}, intent="шаг, которого не будет"),
        Step(organ="echo-a", tool="echo", payload={"data": "шаг-2"}, intent="тоже не будет"),
    ],
    trace_id="wave24-scene2-stop-between",
)
assert done is False
s2 = [e["type"] for e in journal.by_trace("wave24-scene2-stop-between")]
assert s2.count("act") == 1, s2
assert s2[-1] == "halt", s2
halt2 = [e for e in journal.by_trace("wave24-scene2-stop-between") if e["type"] == "halt"][0]
assert halt2["payload"]["source"] == "external" and halt2["payload"]["at_step"] == 1, halt2["payload"]
print("сцена 2 (стоп между шагами): шаг 0 — act/observe/reflect в крови, halt at_step=1, шаги 1–2 не начинались")

# --- Сцена 3: сигнал молчит — трейс проходит целиком --------------------------
calm_house = Loop(gateway, journal, stop_signal=lambda: None)
done = calm_house.run(
    [Step(organ="echo-a", tool="echo", payload={"data": "спокойно"}, intent="обычный трейс")],
    trace_id="wave24-scene3-no-stop",
)
assert done is True
assert not [e for e in journal.by_trace("wave24-scene3-no-stop") if e["type"] == "halt"]
print("сцена 3 (сигнал молчит): run=True, halt = 0 — прежние семантики живы (аддитивно)")

# --- Сцена 4: упавший сигнал — тоже стоп (fail-closed) ------------------------


def broken_signal() -> str | None:
    raise RuntimeError("нерв оборван")


broken_house = Loop(gateway, journal, stop_signal=broken_signal)
done = broken_house.run(
    [Step(organ="echo-a", tool="echo", payload={"data": "s4"}, intent="шаг при оборванном нерве")],
    trace_id="wave24-scene4-broken-signal",
)
assert done is False
halt4 = [e for e in journal.by_trace("wave24-scene4-broken-signal") if e["type"] == "halt"][0]
assert "стоп-сигнал упал" in halt4["payload"]["reason"] and "нерв оборван" in halt4["payload"]["reason"], halt4
assert not [e for e in journal.by_trace("wave24-scene4-broken-signal") if e["type"] == "act"]
print("сцена 4 (упавший сигнал): halt «стоп-сигнал упал: …» до факта, act = 0")

# --- Сцена 5: файловый нерв живого хоста --------------------------------------
stop_file = HERE / "stop-demo.txt"
stop_file.write_text("Человек остановил организм\n", encoding="utf-8")
file_house = Loop(gateway, journal, stop_signal=file_stop_signal(stop_file))
done = file_house.run(
    [Step(organ="echo-a", tool="echo", payload={"data": "s5"}, intent="шаг под стоп-файлом")],
    trace_id="wave24-scene5-file-nerve",
)
assert done is False
halt5 = [e for e in journal.by_trace("wave24-scene5-file-nerve") if e["type"] == "halt"][0]
assert halt5["payload"]["source"] == "external" and "Человек остановил организм" in halt5["payload"]["reason"], halt5
assert not stop_file.exists(), "стоп-файл обязан быть потреблён: остановка живёт в крови"
# файл потреблён — следующий трейс тем же нервом проходит до конца
done = file_house.run(
    [Step(organ="echo-a", tool="echo", payload={"data": "s5b"}, intent="трейс после потребления сигнала")],
    trace_id="wave24-scene5-file-nerve-resume",
)
assert done is True
print("сцена 5 (файловый нерв): причина прочитана из файла, halt source=external; файл потреблён — следующий трейс жив")

# --- Сцена 6: живая проба гейта spec-drift (W-0030) ---------------------------
import importlib.util  # noqa: E402

doctor_spec = importlib.util.spec_from_file_location("doctor-live", REPO_ROOT / "scripts" / "doctor.py")
doctor = importlib.util.module_from_spec(doctor_spec)
sys.modules["doctor-live"] = doctor
doctor_spec.loader.exec_module(doctor)

probe = Path(tempfile.mkdtemp(prefix="wave24-spec-drift-"))
subprocess.run(["git", "-C", str(probe), "init", "-q"], check=True)
(probe / "README.md").write_text("проба гейта\n", encoding="utf-8")
subprocess.run(["git", "-C", str(probe), "-c", "user.email=r@r", "-c", "user.name=r", "add", "-A"], check=True)
subprocess.run(["git", "-C", str(probe), "-c", "user.email=r@r", "-c", "user.name=r", "commit", "-q", "-m", "base"], check=True)
# поведение без спеки — красный
(probe / "blood").mkdir()
(probe / "blood" / "envelope.py").write_text("x = 1\n", encoding="utf-8")
ok_red, fleas_red = doctor.check_spec_drift(probe)
assert ok_red == 0 and any("blood/envelope.py" in f for f in fleas_red), fleas_red
# спека догнала код — зелёный
(probe / "specs").mkdir()
(probe / "specs" / "SPEC-0003-blood-envelope.md").write_text("догнала\n", encoding="utf-8")
ok_green, fleas_green = doctor.check_spec_drift(probe)
assert (ok_green, fleas_green) == (1, []), fleas_green
# fail-closed: папки с git нет — красный без суждения
ok_none, fleas_none = doctor.check_spec_drift(HERE / "нет-такой-папки-git")
assert ok_none == 0 and fleas_none, "гейт без git обязан быть красным, не слепым"
print("сцена 6 (spec-drift живьём): поведение без спеки — красный; спека догнала — зелёный; без git — fail-closed красный")

# --- Чтение своей крови: дневник ----------------------------------------------
diary_report = entries(journal)
rendered = render(journal)
(HERE / "output.md").write_text(rendered, encoding="utf-8")
assert "стоп" in rendered, "дневник обязан назвать остановку словами"
print("дневник: кровь волны прочитана — output.md записан")

journal.append(make(
    event_type="reflect",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "criterion": "6 сцен живьём: стоп до старта/между шагами/молчание/обрыв нерва/файловый нерв + живая проба spec-drift (красный без спеки, зелёный со спекой, fail-closed без git)",
        "verdict": "стоп-кран живёт снаружи и named в крови (source=external); сделанное до стопа не вычёркивается; упавший сигнал не молчит; принцип «спека раньше кода» стал машиной",
        "honesty": "сигналы — подставки (named в boot); орган — фейк; проба spec-drift — на временной копии дома, гейт дома зелёный своим диффом",
        "next": "W-0036 (матрица приоритета законов), W-0031 (PIDLock против зомби-владельца), W-0028 (А/Б против разумной базы Б2)",
    },
    cost=Cost(),
    idempotency_key="wave24-stop-drift-reflect",
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
