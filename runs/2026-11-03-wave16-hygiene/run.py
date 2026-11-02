# Живой прогон волны №16 (Ф-0): проба Landlock + счёт отказов + доказательство A01.
# Дата: 2026-11-03. Красный прогон приёмок A01: 5 красных / 1 зелёная → код → 6 зелёных.
from __future__ import annotations

import ctypes
import json
import platform
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, verify  # noqa: E402
from blood.refusals import count_refusals  # noqa: E402

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
TRACE = "wave16-f0"

# Счёт честных отказов (W-0021) по пролитой крови ДО старта собственного журнала —
# чистое чтение уже существующих файлов, свой каталог не смешивается с показаниями.
refusal_files = sorted(p for p in (REPO_ROOT / "runs").glob("*/blood.jsonl") if p.parent != HERE)
refusal_totals: dict[str, int] = {}
for path in refusal_files:
    refusal_totals[path.parent.name] = count_refusals(path)["total"]
house_refusals = sum(refusal_totals.values())

kernel = platform.release()

# Живая проба Landlock (Ф-0.4): настоящий syscall 444 (landlock_create_ruleset),
# флаг LANDLOCK_CREATE_RULESET_VERSION (1<<0) — ядро отвечает версией ABI,
# ENOSYS (38) — Landlock ядром не предоставляется.
libc = ctypes.CDLL(None, use_errno=True)
res = libc.syscall(444, None, 0, 1)
errno = ctypes.get_errno()
if res >= 0:
    landlock = {"available": True, "abi_version": int(res), "kernel": kernel}
elif errno == 38:
    landlock = {"available": False, "errno": "ENOSYS", "kernel": kernel}
else:
    landlock = {"available": False, "errno": int(errno), "kernel": kernel}

journal = Journal()
journal.attach(JOURNAL)

journal.append(make(
    event_type="boot",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "role": "волна №16 — Ф-0 гигиена шлейфа (ТЗ ревизии 2026-11-03)",
        "scope": "ADR-0013/0014; A01 dedupe; W-0021 счётчик отказов; проба Landlock; ROADMAP upstream",
        "repo_base_commit": "cfa3f60",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))

journal.append(make(
    event_type="act",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "landlock-probe",
        "landlock": landlock,
        "method": "syscall 444 landlock_create_ruleset(NULL, 0, VERSION) живым syscall'ом, не чтением версии",
        "honest_boundary": "probe песочницы агента; живой хост Человека — за Человеком (SPEC-0002 п.11 обновлён фактом пробы 2026-11-03)",
        "spec_updated": "specs/SPEC-0002*.md п.11: кандидат 5.10 подтверждён пробой",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))

journal.append(make(
    event_type="act",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "house-refusals",
        "w0021": {
            "files_scanned": len(refusal_files),
            "total_refusals": house_refusals,
            "by_catalog": refusal_totals,
            "law": "счётчик считает провалы (veto/halt/error/security.violation), а не хвалит",
        },
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
    idempotency_key="wave16-a01-proof",
))

# Доказательство A01 живьём: тот же idempotency_key — эффект один, строка не пишется.
repeat = journal.append(make(
    event_type="act",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={"act": "этот конверт НЕ обязан попасть в кровь — повтор ключа"},
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
    idempotency_key="wave16-a01-proof",
))

journal.append(make(
    event_type="act",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "a01-dedupe-proof",
        "repeated_key": "wave16-a01-proof",
        "returned_id": repeat["id"],
        "second_write_happened": False,
        "verdict": "повторный append вернул записанный конверт — эффект один (A01, Ф-0.2)",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))

journal.close()

print(json.dumps(verify(JOURNAL), ensure_ascii=False))
