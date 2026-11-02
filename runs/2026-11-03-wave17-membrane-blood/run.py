# Живой прогон волны №17, такт 2 (стык): адаптер контракта пакета, конвенции
# чтения, A02/A17, донорский свип. Ядро честного происхождения служено тактом 1
# (runs/2026-11-03-wave17-origin — база принята). Кровь перелита под семантику
# такта 1 до вливания в общий дом (файл не был запушен) — честно названо в отчёте.
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.adapter import import_event  # noqa: E402
from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, verify  # noqa: E402
from blood.provenance import event_time, privacy_of, trust_of  # noqa: E402

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
TRACE = "wave17-t2"

journal = Journal()
journal.attach(JOURNAL)

journal.append(make(
    event_type="boot",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "role": "волна №17 такт 2 — стык: адаптер контракта пакета, конвенции чтения, донорский свип",
        "scope": "SPEC-0003 п.11 (адаптер, провенанс чтения); A02/A17; восстановление книжек после параллельного коммита",
        "repo_base_commit": "7dc173f",
        "note": "саморождённое событие не выдумывает время факта — поле occurred_at отсутствует, незаявленное не ставится (п.10)",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))

# 1. Импорт известного события контракта пакета: факт коллеги старше приёма —
#    хронология честной записи (occurred_at < observed_at <= stored_at) видна в крови.
membrane_event = {
    "event_id": "mem-e-1001",
    "event_name": "act",
    "schema_version": "0.1.0",
    "occurred_at": "2026-11-02T10:00:00Z",
    "observed_at": "2026-11-02T10:00:01Z",
    "stored_at": "2026-11-02T10:00:02Z",
    "source": "colleague-llm",
    "sequence": 7,
    "correlation_id": "corr-1",
    "causation_id": "mem-cause-77",
    "payload": {"what": "внешний акт коллеги, донесённый по контракту"},
    "cost": {"tokens": 5, "duration_ms": 12},
    "trust": "verified",
    "privacy": "personal",
}
imported_stored = journal.append(import_event(
    membrane_event, trace_id=TRACE, cost=Cost(0, 0, 0.001),
))

journal.append(make(
    event_type="observe",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "membrane-import-known",
        "imported_event_name": "act",
        "their_fact_time_carried": imported_stored["occurred_at"],
        "chronology_visible_in_blood": imported_stored["occurred_at"] < imported_stored["observed_at"] <= imported_stored["stored_at"],
        "house_observed_at_is_reception": imported_stored["observed_at"] != membrane_event["observed_at"],
        "their_causation_not_house_uuid": "causation_id" not in imported_stored,
        "trust_privacy_carried": [trust_of(imported_stored), privacy_of(imported_stored)],
        "their_claims_are_provenance": imported_stored["payload"]["membrane"],
        "verdict": "факт коллеги (02.11 10:00Z) старше приёма домом — задержка наблюдения видна в крови; их заявки — провенанс, не факты дома (п.11)",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
    causation_id=imported_stored["id"],
))

# 2. A17 живьём: неизвестное событие сохраняется, не исполняется (ADR-0014).
stranger = dict(membrane_event, event_name="consciousness.surge")
unknown_envelope = journal.append(import_event(stranger, trace_id=TRACE))

journal.append(make(
    event_type="observe",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "membrane-import-unknown",
        "original_event_name": "consciousness.surge",
        "house_type": unknown_envelope["type"],
        "original_preserved_in_payload": unknown_envelope["payload"]["original"]["event_name"],
        "executed_as_foreign_type": len(journal.by_type("consciousness.surge")) > 0,
        "verdict": "сохранено error-конвертом, не исполнено — чужой тип в крови не живёт (A17, ADR-0014)",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
    causation_id=unknown_envelope["id"],
))

# 3. A02 живьём: неизвестное время остаётся UNKNOWN — явный null в крови, не выдумка.
unknown_time = journal.append(make(
    event_type="observe",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "a02-unknown-fact-time",
        "fact": "факт донесён без момента — время события неизвестно",
        "occurred_at_in_blood": None,
        "event_time_reader_sees": event_time({"occurred_at": None}),
        "verdict": "неизвестное время осталось UNKNOWN: null, не фиктивная отметка (A02, п.10)",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
    occurred_at=None,
))

# 4. Конвенции чтения живьём: незаявленное не достраивается — старая кровь
#    и конверт без заявки читаются честно (unknown / sensitive наружу).
journal.append(make(
    event_type="act",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "read-conventions-proof",
        "self_born_declares_no_fact_time": "occurred_at" not in unknown_time,
        "reader_sees_unknown_fact_time": event_time(unknown_time) is None,
        "reader_trust_of_unclassified": trust_of(unknown_time),
        "reader_privacy_of_unclassified_outward": privacy_of(unknown_time),
        "verdict": "незаявленное не выдумывается ни письмом, ни чтением; недоклассифицированное наружу = sensitive (fail-closed наружу, п.10)",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))

# 5. Донорский свип 03.11 живым REST API (триггер тишины langchain#41624).
journal.append(make(
    event_type="act",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "donor-sweep",
        "method": "REST GET живым API, только чтение; HTTP 200 на всех точках",
        "points_checked": {
            "langchain#41624": "OPEN, assignees пусты, наш комм. 02.11 13:31Z — единственный в треде",
            "langchain#41632": "CLOSED ботом require-issue-link 02.11 13:26Z, коммит f0be70d жив в форке",
            "n8n-docs#5689": "OPEN, mergeable, REVIEW_REQUIRED — ждёт человека",
            "markitdown#2808": "OPEN, mergeable, ревью нет — старшие очереди живы",
            "markitdown#2810": "OPEN, mergeable, ревью нет",
            "shadcn#12568": "OPEN, не смерджен, очередь #12567 занята",
        },
        "silence_trigger": {
            "issue": "langchain#41624",
            "full_days_of_silence": 0,
            "hours_since_last_house_comment": 7.4,
            "fired": False,
            "followup_window": "04.11 ~16:31 МСК (2 дня) — 05.11 ~16:31 МСК (3 дня)",
        },
        "verdict": "триггер тишины не сработал — не пинговать раньше тишины (правило донорской книги)",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))

journal.append(make(
    event_type="reflect",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "verdict": "такт 2 служен: адаптер контракта пакета (п.11), конвенции чтения, книжки дома восстановлены",
        "acceptances": "A02 (неизвестное время UNKNOWN) и A17 (сохранено, не исполнено) — оба режима ADR-0014",
        "spec": "SPEC-0003 п.11 (адаптер и провенанс чтения) поверх п.10 такта 1",
        "tests": "tests/test_blood_provenance.py — 20 приёмок стыка; полный сюит зелёный",
        "next": "PR-2 — дневник человека (W-0023): кровь, переведённая на человеческий",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
    idempotency_key="wave17-t2-reflect",
))

journal.close()

print(json.dumps(verify(JOURNAL), ensure_ascii=False, indent=2))
