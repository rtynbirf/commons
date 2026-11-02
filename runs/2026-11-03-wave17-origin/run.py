# Живой прогон волны №17 (Ф-1.1): конверт честного происхождения (W-0022, SPEC-0003 п.9).
# Дата: 2026-11-03. Красный прогон приёмок: 10 красных / 2 зелёные на нетронутом коде → код → 12 зелёных.
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import Cost, EnvelopeError, make, now_utc  # noqa: E402
from blood.journal import Journal, verify  # noqa: E402

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
TRACE = "wave17-origin"

failures: list[str] = []


def check(name: str, ok: bool, detail: str) -> None:
    if not ok:
        failures.append(f"{name}: {detail}")


def iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


journal = Journal()
journal.attach(JOURNAL)

# --- Сцена 0: boot — конверт старого стиля: полей происхождения не несёт
# (аддитивность живьём: один файл крови смешивает старый стиль и происхождение).
boot = journal.append(make(
    event_type="boot",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "role": "волна №17 — Ф-1.1 конверт честного происхождения (ТЗ ревизии, W-0022)",
        "repo_base_commit": "620076e",
        "style": "старый контур: без полей происхождения — кровь v0.4/v0.5 валидна навсегда",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))
check("boot", "stored_at" in boot and "trust" not in boot, "журнал обязан ставить stored_at и не выдумывать классы")

# --- Сцена 1: наблюдение внешнего мира (verified).
# Факт случился раньше, чем тело его увидело: mtime README.md — occurred_at;
# observed_at — момент stat; stored_at ставит журнал. Тело видело само → verified.
readme = REPO_ROOT / "README.md"
st = readme.stat()
occurred = datetime.fromtimestamp(st.st_mtime, timezone.utc)
observed_at = now_utc()
readme_event = journal.append(make(
    event_type="observe",
    source="brainstem",
    organ="markitdown",
    trace_id=TRACE,
    payload={
        "file": "README.md",
        "size_bytes": st.st_size,
        "mtime_utc": occurred.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "sense": "stat — тело увидело файл само",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
    occurred_at=occurred.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    observed_at=observed_at,
    trust="verified",
    privacy="internal",
))
check(
    "triple-time",
    iso(readme_event["occurred_at"]) < iso(readme_event["observed_at"]) <= iso(readme_event["stored_at"]),
    f"{readme_event['occurred_at']} < {readme_event['observed_at']} <= {readme_event['stored_at']}",
)

# --- Сцена 2: весть от чужих (unverified) — самоотчёт пакета о самом себе.
# Пакет «Human Membrane» заявляет в своём STATUS_LEDGER, что Этап 8 не построен.
# Это весть пакета о пакете: здесь, в этом прогоне, тело её не перепроверяло —
# самоотчёт не повышает статус (инвариант 24). Честный класс — unverified.
claim_event = journal.append(make(
    event_type="observe",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "claim": "пакет Human Membrane v0.1.0 заявляет: Этап 8 (внешний человек) — NOT_BUILT",
        "claim_source": "STATUS_LEDGER пакета (самоотчёт)",
        "checked_here": False,
        "law": "самоотчёт ≠ факт: REPO_FACT/UNKNOWN, не повышение статуса",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
    observed_at=now_utc(),
    occurred_at=None,  # когда пакет составил свой ledger — неизвестно, честный UNKNOWN
    trust="unverified",
    privacy="public",
))
check("unverified-null-occurred", claim_event["occurred_at"] is None, "null = честный UNKNOWN")

# --- Сцена 3: личный документ Человека (privacy: personal).
# Вход первого пульса — документ, который дал Человек: метаданные читаем,
# содержимое не трогаем и в кровь не пишем. Класс — personal.
pulse_input = REPO_ROOT / "runs" / "2026-11-01-first-pulse" / "input" / "pulse-input.docx"
pst = pulse_input.stat()
personal_event = journal.append(make(
    event_type="observe",
    source="brainstem",
    organ="markitdown",
    trace_id=TRACE,
    payload={
        "file": "runs/2026-11-01-first-pulse/input/pulse-input.docx",
        "size_bytes": pst.st_size,
        "sense": "только метаданные документа Человека; содержимое в кровь не пишется",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
    occurred_at=datetime.fromtimestamp(pst.st_mtime, timezone.utc)
    .isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    observed_at=now_utc(),
    trust="verified",
    privacy="personal",
))

# --- Сцена 4: выведено из крови (derived) + семантическая причинность.
# Сумма цены этого трейса — вывод ИЗ крови: derived; causation_id называет
# событие-родитель, полный набор — payload.derived_from.
before = journal.all()
derived_from = [e["id"] for e in before if e["type"] in ("observe", "boot")]
totals = journal.totals(TRACE)
derived_event = journal.append(make(
    event_type="reflect",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "reflection": "цена трейса выведена из крови этого прогона",
        "totals": totals.as_dict(),
        "derived_from": derived_from,
        "law": "derived — выведено телом из пролитой крови, не весть и не наблюдение",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
    observed_at=now_utc(),
    causation_id=before[-1]["id"],
    trust="derived",
    privacy="internal",
))
check("causation", derived_event["causation_id"] == before[-1]["id"], "семантический родитель назван")

# --- Сцена 5: fail-closed живьём — неизвестный класс не доходит до крови.
rejections = []
for field, bad in (("trust", "по-честному-не-знаю"), ("privacy", "совершенно-секретно")):
    try:
        make(
            "act", "brainstem", "self", TRACE, {}, Cost(),
            **{field: bad},
        )
        rejections.append(f"{field}: НЕ ОТВЕРГНУТ — дыра")
        failures.append(f"fail-closed {field}: неизвестный класс прошёл")
    except EnvelopeError as exc:
        rejections.append(f"{field}: EnvelopeError ({str(exc).split(':')[1].strip()[:60]}...)")
# Отказ честно в крови: запись не состоялась, конверт-отчёт — не подделка.
rejection_event = journal.append(make(
    event_type="error",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "error": "неизвестные классы происхождения отвергнуты при записи (fail-closed, ADR-0014)",
        "rejections": rejections,
        "written": False,
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
    observed_at=now_utc(),
    causation_id=derived_event["id"],
    trust="verified",
    privacy="internal",
))

# --- Итог: целостность и перечитывание.
journal.close()
report = verify(JOURNAL)
check("verify", report["gaps"] == [] and report["chained"], json.dumps(report, ensure_ascii=False))
reread = Journal.from_jsonl(JOURNAL)
check("reread", reread.skipped == 0, f"skipped={reread.skipped}")

# Хронология всей крови с тройным временем: occurred <= observed <= stored.
origin_events = [e for e in reread if "observed_at" in e and "stored_at" in e]
for e in origin_events:
    occ, obs, sto = iso(e.get("occurred_at")), iso(e["observed_at"]), iso(e["stored_at"])
    if occ is not None:
        check(f"chronology {e['id'][:8]}", occ <= obs <= sto, f"{occ} <= {obs} <= {sto}")

print(json.dumps({
    "verify": report,
    "events": len(reread),
    "origin_events": len(origin_events),
    "fail_closed_rejections": rejections,
    "failures": failures,
    "verdict": "ЧИСТО" if not failures else "КРАСНО",
}, ensure_ascii=False, indent=2))
