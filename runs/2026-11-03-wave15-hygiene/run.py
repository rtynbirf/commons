"""Контрольный забег Ф-0 — стык волн №15/№16 (2026-11-03).

История: параллельный забег волны №15 закрыл Ф-0 независимо (свой журнал-
память, свой счётчик, свои ADR) — и отступил принятой базе волны №16 по
стык-дисциплине волны №13 («их релизы сохранены, параллельный вариант
отступает более консервативному решению»). Их решения точнее в двух местах:
живая проба Landlock живым syscall 444 (моя была uname-версией) и разведение
режимов A17 через append-only файл (ADR-0014). Остаток дельты забега —
контрольная ценность: сцены ниже гоняются на ИХ коде (blood.refusals,
их память dedupe) — независимая перекрёстная проверка Ф-0 третьим путём.

Сцены (факты, не предсказания):

1. A01 дедуп: повторный append с тем же idempotency_key не повторяет эффект;
2. A01 resume: дедуп переживает reopen — ключ не дописывает копию;
3. A01 обратная совместимость: конверт без ключа живёт как прежде;
4. A01 разные ключи при одинаковой нагрузке — два конверта (ключ — имя
   намерения, не содержимое);
5. W-0021 живая кровь А/Б их счётчиком: veto/halt/error/security.violation —
   сверено с ручным подсчётом (error 3, halt 3, security.violation 3);
6. W-0021 живая кровь red-run их счётчиком (veto 2, halt 2, error 5,
   security.violation 3);
7. W-0021 знаменатель: отказы против всех конвертов и трейсов;
8. Landlock-проба: согласованность показаний ядра (их живой syscall-факт
   в SPEC-0002 п.11);
9. кровь забега: цепочка prev_id цела — verify: 0 гэпов, chained=true.

Кровь забега пишется тем же журналом: runs/2026-11-03-wave15-hygiene/blood.jsonl.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import make  # noqa: E402
from blood.refusals import count_refusals  # noqa: E402
from blood.journal import Journal, verify  # noqa: E402

RUN_DIR = Path(__file__).resolve().parent
BLOOD_PATH = RUN_DIR / "blood.jsonl"

GREEN: list[str] = []
RED: list[str] = []

BLOOD_JOURNAL = Journal()
BLOOD_JOURNAL.attach(BLOOD_PATH)
TRACE = "wave15-crosscheck"


def verdict(ok: bool, name: str, detail: str) -> None:
    (GREEN if ok else RED).append(f"{name}: {detail}")
    kind = "reflect" if ok else "error"
    BLOOD_JOURNAL.append(
        make(kind, "wave15", "self", TRACE, {"scene": name, "detail": detail, "verdict": "green" if ok else "red"})
    )
    print(f"[ЗЕЛЁНО] {name}: {detail}" if ok else f"[КРАСНО] {name}: {detail}")


def fact(name: str, detail: str) -> None:
    BLOOD_JOURNAL.append(make("observe", "wave15", "self", TRACE, {"scene": name, "detail": detail}))
    print(f"[ФАКТ] {name}: {detail}")


def scene_plan(name: str, index: int) -> None:
    BLOOD_JOURNAL.append(make("plan", "wave15", "self", TRACE, {"scene": name, "index": index}))


# ---------------------------------------------------------------- такт 2/3: сцены

def scene_a01() -> None:
    """A01: повторный append с тем же idempotency_key не повторяет эффект."""
    scene_plan("A01 дедуп", 2)
    path = RUN_DIR / "tmp_a01.jsonl"
    path.unlink(missing_ok=True)
    journal = Journal()
    journal.attach(path)
    first = journal.append(make("act", "brainstem", "self", "a01-trace", {"шаг": 1}, idempotency_key="шаг-1"))
    second = journal.append(make("act", "brainstem", "self", "a01-trace", {"шаг": 1}, idempotency_key="шаг-1"))
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    ok = (
        len(journal) == 1
        and len(lines) == 1
        and second["id"] == first["id"]
    )
    verdict(ok, "A01 дедуп",
            f"повторный ключ: журнал {len(journal)} конверт, файл {len(lines)} строк, id совпал"
            if ok else f"повтор НЕ дал дедупа: журнал {len(journal)}, файл {len(lines)}")
    journal.close()
    path.unlink(missing_ok=True)  # сцена подметает за собой: tmp-артефакт не живёт в доме


def scene_a01_resume() -> None:
    """A01: дедуп переживает reopen — повторный ключ после resume не дописывает."""
    scene_plan("A01 resume", 3)
    path = RUN_DIR / "tmp_a01_resume.jsonl"
    path.unlink(missing_ok=True)
    j1 = Journal()
    j1.attach(path)
    j1.append(make("act", "brainstem", "self", "a01-trace", {"шаг": 1}, idempotency_key="шаг-1"))
    j1.close()
    j2 = Journal()
    j2.attach(path)  # повторная сессия продолжает журнал
    stored_id = json.loads(path.read_text(encoding="utf-8").splitlines()[0])["id"]
    again = j2.append(make("act", "brainstem", "self", "a01-trace", {"шаг": 1}, idempotency_key="шаг-1"))
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    ok = len(lines) == 1 and again["id"] == stored_id and len(j2) == 0
    verdict(ok, "A01 resume",
            f"после reopen ключ не дописал: файл {len(lines)} строк, возвращён id записанного, сессия не пополнилась"
            if ok else f"resume потерял память ключа: файл {len(lines)} строк")
    j2.close()
    path.unlink(missing_ok=True)


def scene_a01_compat() -> None:
    """A01: конверт без ключа живёт как прежде — оба дописаны."""
    scene_plan("A01 совместимость", 4)
    path = RUN_DIR / "tmp_a01_compat.jsonl"
    path.unlink(missing_ok=True)
    journal = Journal()
    journal.attach(path)
    journal.append(make("act", "brainstem", "self", "a01-trace", {"шаг": 1}))
    journal.append(make("act", "brainstem", "self", "a01-trace", {"шаг": 1}))
    ok = len(journal) == 2
    verdict(ok, "A01 совместимость",
            "конверт без ключа дописывается как прежде (2 конверта)"
            if ok else f"совместимость сломана: журнал {len(journal)}")
    journal.close()
    path.unlink(missing_ok=True)


def scene_a01_distinct() -> None:
    """A01: разные ключи — два конверта (ключ называет намерение, не содержимое)."""
    scene_plan("A01 разные ключи", 5)
    path = RUN_DIR / "tmp_a01_distinct.jsonl"
    path.unlink(missing_ok=True)
    journal = Journal()
    journal.attach(path)
    journal.append(make("act", "brainstem", "self", "a01-trace", {"шаг": 1}, idempotency_key="попытка-1"))
    journal.append(make("act", "brainstem", "self", "a01-trace", {"шаг": 1}, idempotency_key="попытка-2"))
    ok = len(journal) == 2
    verdict(ok, "A01 разные ключи",
            "разные ключи — оба конверта в журнале"
            if ok else f"ключи перепутались: журнал {len(journal)}")
    journal.close()
    path.unlink(missing_ok=True)


def scene_honesty_ab_live() -> None:
    """W-0021: их счётчик (blood.refusals) по живой крови А/Б сверён с ручным подсчётом."""
    scene_plan("W-0021 А/Б", 6)
    path = REPO_ROOT / "runs/2026-11-02-wave10-ab-live/blood.jsonl"
    report = count_refusals(path)
    fact("W-0021 А/Б", f"факт счётчика: {json.dumps(report, ensure_ascii=False, sort_keys=True)}")
    ok = (
        report["total"] == 9
        and report["by_type"] == {"error": 3, "halt": 3, "security.violation": 3}
        and len(report["traces"]) == 3
    )
    verdict(ok, "W-0021 А/Б",
            f"error 3 + halt 3 + security.violation 3 = {report['total']}, трейсов с провалами {len(report['traces'])} — сверено с ручным подсчётом"
            if ok else f"счётчик разошёлся с ручным подсчётом: {report}")


def scene_honesty_red_run() -> None:
    """W-0021: живая кровь red-run их счётчиком — все четыре вида провалов."""
    scene_plan("W-0021 red-run", 7)
    path = REPO_ROOT / "runs/2026-11-02-wave10-red-run-live/blood.jsonl"
    report = count_refusals(path)
    fact("W-0021 red-run", f"факт счётчика: {json.dumps(report, ensure_ascii=False, sort_keys=True)}")
    ok = (
        report["by_type"] == {"veto": 2, "halt": 2, "error": 5, "security.violation": 3}
        and report["total"] == 12
    )
    verdict(ok, "W-0021 red-run",
            f"veto 2 + halt 2 + error 5 + security.violation 3 = {report['total']} — все четыре вида названы"
            if ok else f"счётчик разошёлся: {report}")


def scene_honesty_denominator() -> None:
    """W-0021: честный знаменатель — провалы против всех конвертов и трейсов файла."""
    scene_plan("W-0021 знаменатель", 8)
    path = REPO_ROOT / "runs/2026-11-02-wave10-ab-live/blood.jsonl"
    report = count_refusals(path)
    journal = Journal.from_jsonl(path)
    events = len(journal)
    traces = len({e["trace_id"] for e in journal})
    ok = (
        events == 33
        and traces == 3
        and 0 < report["total"] <= events
    )
    verdict(ok, "W-0021 знаменатель",
            f"провалов {report['total']} из {events} конвертов, трейсов с провалами {len(report['traces'])}/{traces} — знаменатель честен"
            if ok else f"знаменатель кривой: events={events}, traces={traces}, {report}")


def scene_landlock() -> None:
    """Такт 4: Landlock-проба живого хоста — факт в кровь и спеку."""
    scene_plan("Landlock проба", 9)
    kernel = platform.release()
    abi_path = Path("/sys/kernel/security/landlock/abi")
    lsm_path = Path("/sys/kernel/security/lsm")
    abi = abi_path.read_text().strip() if abi_path.exists() else None
    lsm = lsm_path.read_text().strip() if lsm_path.exists() else None
    major, minor = (int(p) for p in kernel.split(".")[:2])
    kernel_supports = (major, minor) >= (5, 13)
    available = abi is not None
    fact("Landlock проба",
         f"ядро {kernel}; /sys/kernel/security/landlock/abi {'есть: ' + abi if abi else 'нет'}; "
         f"lsm: {lsm or 'не прочитан'}; порог спеки 5.13; "
         f"вердикт: {'доступен' if available else 'НЕДОСТУПЕН на этом хосте'}; "
         f"их живой факт волны №16: syscall 444 landlock_create_ruleset -> ENOSYS (SPEC-0002 п.11)")
    ok = (not kernel_supports and not available) or (kernel_supports and available)
    verdict(ok, "Landlock проба",
            f"ядро {kernel} ({'< 5.13 — Landlock не мог встать' if not kernel_supports else '>= 5.13'}) "
            f"и ABI {'поднят' if available else 'не поднят'} — показания согласованы, факт в спеке SPEC-0002 п.11"
            if ok else f"показания противоречивы: ядро {kernel}, ABI {abi}")


def main() -> int:
    BLOOD_JOURNAL.append(make("boot", "wave15", "self", TRACE, {
        "wave": "№15 гигиена шлейфа (Ф-0)",
        "directive": "ГОНИ ВОЛНУ, КОСЯКИ ПРАВЬ — ОБРАЗЦОВО ПОКАЗАТЕЛЬНОЕ РЕПО",
        "tacts": ["ADR-0013/0014", "A01 идемпотентность", "W-0021 счётчик отказов", "Landlock проба", "ROADMAP честно"],
    }))
    print("=== ВОЛНА №15: ГИГИЕНА ШЛЕЙФА ===")

    fact("Такт 1", "ADR-0013 (словарь: орган/бюджет/полномочия) и ADR-0014 (неизвестный тип крови) приняты, словарь дополнен")

    scene_a01()
    scene_a01_resume()
    scene_a01_compat()
    scene_a01_distinct()
    scene_honesty_ab_live()
    scene_honesty_red_run()
    scene_honesty_denominator()
    scene_landlock()

    BLOOD_JOURNAL.append(make("reflect", "wave15", "self", TRACE, {
        "зелёных": len(GREEN),
        "красных": len(RED),
        "вердикт": "волна зелёная" if not RED else "волна красная",
    }))
    report = verify(BLOOD_PATH)
    chained = report["chained"] and not report["gaps"]
    verdict(chained, "Кровь волны",
            f"{report['events']} конвертов, 0 гэпов, цепочка prev_id цела"
            if chained else f"кровь битая: {report}")

    BLOOD_JOURNAL.close()
    print(f"\nИТОГ: {len(GREEN)} зелёных / {len(RED)} красных")
    for line in RED:
        print(f"  КРАСНО: {line}")
    return 1 if RED else 0


if __name__ == "__main__":
    sys.exit(main())
