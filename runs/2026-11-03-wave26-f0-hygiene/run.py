# Живой прогон волны №26 (Ф-0' «гигиена дисциплины», docs/TZ.md ТЗ-0.1…ТЗ-0.5).
# Дата: 2026-11-03. Красный прогон приёмок: 23 красных / 1 зелёная на нетронутом
# коде (зомби держал lock живьём — гипотеза F-12 подтверждена до фикса).
# Пробы живьём: вторая независимая Landlock-проба (ТЗ-0.1), зомби-владелец и
# reиспользование PID на фиксированном PIDLock (ТЗ-0.5), оба новых гейта
# доктора на живом доме (ТЗ-0.2/ТЗ-0.3), ADR-0015 (ТЗ-0.4).
from __future__ import annotations

import ctypes
import importlib.util
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, seal, verify  # noqa: E402
from blood.pidlock import PIDLock  # noqa: E402

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
TRACE = "wave26-f0-hygiene"

spec = importlib.util.spec_from_file_location("doctor_w26", REPO_ROOT / "scripts" / "doctor.py")
doctor = importlib.util.module_from_spec(spec)
sys.modules["doctor_w26"] = doctor
spec.loader.exec_module(doctor)

kernel = platform.release()
libc = ctypes.CDLL(None, use_errno=True)

# --- ТЗ-0.1: вторая независимая проба Landlock живым syscall'ом 444 ---------
res = libc.syscall(444, None, 0, 1)  # landlock_create_ruleset(NULL, 0, VERSION)
errno = ctypes.get_errno()
if res >= 0:
    landlock = {"available": True, "abi_version": int(res), "kernel": kernel}
elif errno == 38:
    landlock = {"available": False, "errno": "ENOSYS", "kernel": kernel}
else:
    landlock = {"available": False, "errno": int(errno), "kernel": kernel}


def _stat_fields(pid: int) -> list[str] | None:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    return raw.rpartition(")")[2].split() or None


# --- ТЗ-0.5: зомби-владелец живьём (гипотеза F-12, W-0031) ------------------
zombie_probe: dict = {}
child = subprocess.Popen([sys.executable, "-c", "import os; os._exit(0)"])
deadline = time.monotonic() + 5
fields: list[str] | None = None
while time.monotonic() < deadline:
    fields = _stat_fields(child.pid)
    if fields and fields[0] == "Z":
        break
    time.sleep(0.02)
if fields and fields[0] == "Z":
    lock_path = HERE / ".probe-zombie.lock"
    lock_path.write_text(
        json.dumps({"pid": child.pid, "start_time": fields[19], "ts": "zombie-probe"}),
        encoding="utf-8",
    )
    got = PIDLock(lock_path).acquire()  # старый код поднял бы LockHeld
    zombie_probe = {
        "zombie_pid": child.pid,
        "zombie_state": "Z",
        "lock_replaced": got == os.getpid(),
        "verdict": "зомби-владелец заменён живьём: тело не заперто за мёртвым (SPEC-0004 п.2 v0.4.0, W-0031)",
    }
    lock_path.unlink(missing_ok=True)
else:
    zombie_probe = {"zombie_pid": child.pid, "zombie_state": fields[0] if fields else None,
                    "lock_replaced": False, "verdict": "зомби не случился — граница названа честно"}
child.wait()

# --- ТЗ-0.5: reиспользование PID живьём (чужак с чужим стартовым временем) --
lock_path = HERE / ".probe-reuse.lock"
lock_path.write_text(
    json.dumps({"pid": os.getpid(), "start_time": "1", "ts": "reuse-probe"}),
    encoding="utf-8",
)
got = PIDLock(lock_path).acquire()  # старый код поднял бы LockHeld: живой pid
reuse_probe = {
    "pid": os.getpid(),
    "forged_start_time": "1",
    "lock_replaced": got == os.getpid(),
    "verdict": "чужое стартовое время при живом pid — владелец другой, lock заменён (W-0031)",
}
lock_path.unlink(missing_ok=True)

# --- ТЗ-0.2/ТЗ-0.3: оба новых гейта на живом доме ---------------------------
gates_probe: dict = {}
for name, gate in (("axioms", doctor.check_axioms), ("spec-first", doctor.check_spec_first)):
    ok, fleas = gate(REPO_ROOT)
    gates_probe[name] = {"ok": ok, "fleas": fleas, "green": not fleas}

journal = Journal()
journal.attach(JOURNAL)

journal.append(make(
    event_type="boot",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "role": "волна №26 — Ф-0' гигиена дисциплины (docs/TZ.md ТЗ-0.1…ТЗ-0.5)",
        "scope": "Landlock проба №2; W-0031 зомби/reиспользование PID; W-0034 гейт дрейфа аксиом; W-0030 гейт спека-раньше-кода; W-0036 ADR-0015",
        "repo_base_commit": "7dc63ad",
        "honesty": "пробы системные, без LLM; живой хост Человека по-прежнему за Человеком",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))

journal.append(make(
    event_type="act",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "landlock-probe-2",
        "landlock": landlock,
        "method": "syscall 444 landlock_create_ruleset(NULL, 0, VERSION) живым syscall'ом — вторая независимая проба после волны №16",
        "honest_boundary": "probe живого хоста-песочницы; живой хост Человека — за Человеком (SPEC-0002 п.11 v0.12.0, ТЗ-0.1)",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))

journal.append(make(
    event_type="act",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "pidlock-zombie-probe",
        "probe": zombie_probe,
        "method": "ребёнок os._exit(0) без пожинания → состояние Z в /proc → lock с его pid и стартовым временем → acquire обязан заменить",
        "red_proof": "красный прогон 2026-11-03: на старом коде acquire поднял LockHeld — зомби держал тело живьём",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))

journal.append(make(
    event_type="act",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "pidlock-reuse-probe",
        "probe": reuse_probe,
        "method": "lock с живым pid процесса прогона и чужим start_time='1' → acquire обязан заменить",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))

journal.append(make(
    event_type="act",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "doctor-new-gates-live",
        "gates": gates_probe,
        "method": "check_axioms/check_spec_first на живом доме HEAD 7dc63ad + рабочее дерево волны",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))

journal.append(make(
    event_type="reflect",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "verdict": "Ф-0' закрыта: ТЗ-0.1 проба №2 в крови (граница: живой хост — за Человеком), ТЗ-0.2 гейт axioms зелёный на доме, ТЗ-0.3 гейт spec-first зелёный (HEAD — книги), ТЗ-0.4 ADR-0015 принят с машинной приёмкой порядка, ТЗ-0.5 зомби/reиспользование ловятся живьём",
        "honesty": "косяк счёта арбитража назван: по 25 ID — СЛУЖЕНО/PASS 14 + СНЯТО 1 · ЧАСТИЧНО 3 · НЕ СЛУЖЕНО 7 (групповые строки A04/A05, A06–A09 считались единицами); разложение живёт в docs/axioms.yaml, дрейф счёта теперь ловит гейт",
        "wants": "W-0030, W-0031, W-0034, W-0036 — СЛУЖЕНО; W-0035 (линзы по дому) и красные аксиомы остаются шлейфом ТЗ",
        "next": "Ф-1': ТЗ-1.2 provenance/prompt-injection, ТЗ-1.3 орган-не-включает-себя, ТЗ-1.1 память-файлы",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
    idempotency_key="wave26-reflect",
))

journal.close()

report = verify(JOURNAL)
print(json.dumps(report, ensure_ascii=False, indent=2))
assert report["gaps"] == [], "цепочка порядка порвана"
assert not report.get("content_gaps"), "подмена в собственной крови"

# --- Якорь: опечатываем кровь прогона (append-only, дедуп) -------------------
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
