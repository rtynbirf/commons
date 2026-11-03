# Живой прогон волны №20: верификация советов коллег (внешний аудит 2026-11-03).
# Совет — не факт, факт — замер на живом коде: пробы коллег прогнаны на HEAD
# 0.38.0 до правок (все подтвердились), находки закрыты, пробы прогнаны после
# (контрольный прогон). Кровь волны — здесь, отчёт — report.md.
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, verify  # noqa: E402

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
TRACE = "wave20-colleague-verification"

journal = Journal()
journal.attach(JOURNAL)

journal.append(make(
    event_type="boot",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "role": "волна №20 — верификация советов коллег (внешний аудит 2026-11-03)",
        "scope": "аудит коллег: 12 находок F-01..F-12, патч, репо-пробы; решение Человека: «советы, а не инструкции — вывод брать или не применять, только за нами»",
        "repo_base_commit": "2cc27b8",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))

journal.append(make(
    event_type="act",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "verify-colleague-probes",
        "method": "repro-пробы коллег прогнаны на живом HEAD 0.38.0 до правок",
        "confirmed": [
            "F-01: tamper-in-place и усечение хвоста проходят verify (chained=True) — подмена содержимого не ловится",
            "F-02: несериализуемый payload — TypeError, память 2 конверта против 1 строки файла, _last_id рассинхрон",
            "F-03: эффект без крови — орган вызван, в файле только plan, TypeError вылетел из run() без halt",
            "F-04: os.truncate обнулил файл при fs: read-only; os.symlink/os.link/os.utime не прерваны",
            "F-05: os.listdir/os.scandir/os.stat прошли при fs: none",
            "F-06: {'error':..., 'ok': false} от органа — reflect satisfied=True",
            "F-07: бюджет 1000/10 последним шагом — run()=True без halt",
        ],
        "verdict": "все воспроизводимые находки коллег подтвердились один в один — коллеги правы по фактам",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))

journal.append(make(
    event_type="act",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "arbitration-decision",
        "taken_now": [
            "F-02 закрыт: SPEC-0003 v0.11.0 п.14 — append сериализует ДО мутации, EnvelopeError, отказ записи ничего не меняет",
            "F-04 закрыт: SPEC-0002 v0.11.0 п.8 — полная грамматика мутаций (truncate/symlink/link/utime/setxattr/removexattr), link — оба конца, symlink — создаваемая ссылка",
            "F-05 закрыт: os.listdir/os.scandir при fs: none прерваны (кроме рантайма Python), при скоупе — только внутри корней",
            "F-03 закрыт: Loop валидирует payload шага ДО invoke (эффект не случается без крови) + BloodRecordError в шлюзе — отказной выход завершён halt (G1)",
            "F-01 граница названа честно: докстринг journal.py и приёмка-документация; защита содержимого — хотёлка W-0026 (prev_sha256 + внешний якорь)",
        ],
        "wanted": [
            "W-0026 prev_sha256 (F-01)",
            "W-0027 Step.accept (F-06)",
            "W-0028 А/Б против разумной базы Б2 (F-08)",
            "W-0029 бюджет после последнего шага (F-07)",
            "W-0030 гейт «поведение без спеки» (F-09)",
            "W-0031 PIDLock зомби-владелец (F-12)",
        ],
        "rejected_or_deferred": [
            "README ≤ 60 строк (D6) — решение Человека: README — журнал дома, не вырезать без его слова",
            "Adversarial Verifier как особая роль ствола — только как орган за синапсом после W-0027 (закон 2)",
        ],
        "note": "патч коллег применён по духу дома, не копией: свои приёмки (13), свои докстринги, спека раньше кода; mkfifo/stat — честная граница платформы (audit-событий нет — промерено живьём)",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))

journal.append(make(
    event_type="act",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "post-fix-probes",
        "method": "контрольный прогон тех же проб коллег после правок",
        "results": {
            "F-02": "EnvelopeError, память 1 = файл 1, _last_id цел, цепочка жива",
            "F-03": "run() без исключения, кровь ['plan','halt'] — орган не вызван, трейс полон",
            "F-04": "truncate/symlink/link/utime прерваны, содержимое жертвы цело",
            "F-05": "listdir/scandir при fs: none прерваны; mkfifo/stat — НЕ прерваны (граница платформы, названа в спеке)",
            "F-01": "остаётся (честная граница, W-0026)",
        },
        "suite": "pytest 674 passed (13 новых приёмок), doctor 661 ok / 0 failed",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
))

journal.append(make(
    event_type="reflect",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "verdict": "советы коллег проверены замером: 4 находки закрыты кодом со спекой, 1 названа границей, 6 записаны хотёлками с хозяевами; решение — за домом, а не за чужим патчем",
        "honesty": "F-01 не притворяюсь закрытым: verify по-прежнему не заверяет содержимое — приёмка-документация границы жива в сюите; mkfifo/stat не прерываются и названы границей платформы",
        "grain_taken": "гигиена дома сама поймала хотёлку-сироту W-0026 (гейт wants) — дом ведёт нас за руку",
        "tests": "tests/test_audit_2026_11_03.py — 13 приёмок; полный сюит зелёный",
        "next": "W-0026 prev_sha256 (SPEC-0003 v0.12.0), затем W-0027 Step.accept",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
    idempotency_key="wave20-reflect",
))

journal.close()

report = verify(JOURNAL)
print(json.dumps(report, ensure_ascii=False, indent=2))
