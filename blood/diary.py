"""Дневник человека — read-проекция крови в человеческом языке (W-0023).

SPEC-0003 п.12 (Ф-1.2, волна №18): реконструкция сессии (п.8) машиночитаема
и служит телу; дневник служит Человеку. Каждая запись отвечает по-человечески:
что сделано; кто инициировал; когда; результат; цена; что не сделано; можно ли
отменить; чем подтверждён результат. Честные правила дневника:

- план не показан как исполнение (A05, грех №2467): план — намерение;
  исполнение подтверждается только действием в крови, связанным причинностью;
- «успешно» не пишется без проверяемого результата: действие тела — заявка;
  при trust=unverified дневник говорит «проверок не было», а не «успешно»;
- неизвестное время остаётся «неизвестно» (A02) — фиктивные даты не подставляются;
- отказ — данные, а не стыд (W-0021): veto/halt/error/security.violation
  названы словами, счёт провалов идёт в итог;
- отменяемость честная: компенсатор у дома не построен (W-0024) — дневник
  не обещает отмены;
- кровь не переписывается: дневник — read-проекция; битые строки и гэпы
  цепочки prev_id называются в шапке честно.

Дневник — по-действийный слой зерна «выжимки крови»: W-0019 — агрегат,
дневник — запись; оба — проекции, ни один не пишет в кровь.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Union

from blood.envelope import Cost
from blood.journal import Journal, verify
from blood.provenance import event_time, trust_of

TRUST_WORDS = {
    "unverified": "заявка тела — независимых проверок не было",
    "verified": "проверено",
    "derived": "выведено из крови",
    "unknown": "доверие не заявлено",
}

RESULT_WORDS = {
    "plan": "намерение — не факт",
    "observe": "наблюдение зафиксировано",
    "reflect": "вердикт",
    "veto": "сказано «нет»",
    "halt": "остановлено",
    "error": "ошибка",
    "security.violation": "нарушение полномочий остановлено стражем",
    "boot": "организм проснулся",
    "shutdown": "организм уснул по-записанному",
    "organ.health": "сердцебиение органа",
    "organ.replace": "орган заменён",
    "alert": "сигнал бюджета: порог достигнут",
}


def _what(envelope: dict[str, Any]) -> str:
    """«Что сделано» — человеческое имя действия из payload, не из id."""
    payload = envelope.get("payload") or {}
    for key in ("act", "what", "tool", "reason", "task", "verdict"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return envelope["type"]


def _when(envelope: dict[str, Any]) -> str:
    """Время факта честно: заявленное — как заявлено; незаявленное — неизвестно."""
    fact_time = event_time(envelope)
    if fact_time is None:
        return f"неизвестно (увидено и записано {envelope['ts']})"
    if fact_time == envelope["ts"]:
        return fact_time
    return f"{fact_time} (увидено {envelope.get('observed_at', envelope['ts'])})"


def _result(envelope: dict[str, Any]) -> str:
    """Результат словами; «успешно» появляется только при проверке (A05)."""
    kind = envelope["type"]
    if kind == "act":
        return f"выполнено; {TRUST_WORDS[trust_of(envelope)]}"
    if kind == "reflect":
        verdict = (envelope.get("payload") or {}).get("verdict")
        return f"вердикт: {verdict}" if isinstance(verdict, str) and verdict.strip() else RESULT_WORDS[kind]
    if kind in ("veto", "halt", "error"):
        reason = (envelope.get("payload") or {}).get("reason")
        return f"{RESULT_WORDS[kind]}" + (f"; причина: {reason}" if isinstance(reason, str) and reason.strip() else "")
    return RESULT_WORDS.get(kind, f"событие {kind}")


def _undo(envelope: dict[str, Any]) -> str:
    """Отменяемость честная: компенсатора нет — отмена не обещается (W-0024)."""
    kind = envelope["type"]
    if kind == "plan":
        return "отменять нечего — план не исполнялся"
    if kind in ("observe", "reflect"):
        return "нечего отменять — наблюдение не действие"
    if kind == "act":
        return "отмена не обещается: компенсатор не построен (W-0024)"
    return "системное событие — отмене не подлежит"


def _price(cost: dict[str, Any]) -> str:
    tokens_in = int(cost.get("tokens_in", 0))
    tokens_out = int(cost.get("tokens_out", 0))
    seconds = float(cost.get("seconds", 0.0))
    parts = []
    if tokens_in or tokens_out:
        parts.append(f"токены {tokens_in}/{tokens_out}")
    if seconds:
        parts.append(f"{seconds:g} с")
    return ", ".join(parts) if parts else "нулевая"


def entries(source: Union[Journal, str, Path], trace_id: str | None = None) -> dict[str, Any]:
    """По-действенный слой дневника: кровь → человеческие записи.

    Принимает Journal (память сессии) или путь к blood.jsonl (пролитая
    кровь). Возвращает {"trace_id", "records", "totals", "broken_lines",
    "damaged", "plans_unfulfilled"} — без выдумок: то, чего в крови нет,
    помечено честно.
    """
    if isinstance(source, Journal):
        events = [e for e in source.all() if trace_id is None or e["trace_id"] == trace_id]
        broken = 0
        damage: list[dict[str, Any]] = []  # память сессии — файловая целость не заявляется
    else:
        path = Path(source)
        journal = Journal.from_jsonl(path)
        events = [e for e in journal.all() if trace_id is None or e["trace_id"] == trace_id]
        broken = journal.skipped
        damage = verify(path)["gaps"]  # гэп — свойство файла, показывается при любом фильтре

    acts_by_cause: set[str] = set()
    for e in events:
        cause = e.get("causation_id")
        if e["type"] == "act" and isinstance(cause, str):
            acts_by_cause.add(cause)

    records: list[dict[str, Any]] = []
    plan_ids: set[str] = set()
    unfulfilled = 0
    for e in events:
        record = {
            "что": _what(e),
            "кто инициировал": e["source"],
            "когда": _when(e),
            "результат": _result(e),
            "цена": _price(e["cost"]),
            "можно ли отменить": _undo(e),
            "чем подтверждён": f"{TRUST_WORDS[trust_of(e)]}; конверт {e['id'][:8]}",
        }
        if e["type"] == "plan":
            plan_ids.add(e["id"])
            if e["id"] not in acts_by_cause:
                record["что не сделано"] = "исполнение не подтверждено кровью: действия с причинной связью к плану нет"
                unfulfilled += 1
        records.append(record)

    totals = Cost()
    for e in events:
        totals += Cost.from_dict(e["cost"])

    return {
        "trace_id": trace_id or "все трейсы",
        "records": records,
        "totals": totals.as_dict(),
        "broken_lines": broken,
        "damaged": damage,
        "plans_unfulfilled": unfulfilled,
    }


def render(source: Union[Journal, str, Path], trace_id: str | None = None) -> str:
    """Человеческий текст дневника (markdown): кровь, переведённая на наш язык."""
    book = entries(source, trace_id)
    lines = [
        f"# Дневник — {book['trace_id']}",
        "",
    ]
    if book["damaged"]:
        lines.append(f"**ЖУРНАЛ ПОВРЕЖДЁН: разрывов цепочки {len(book['damaged'])}** — часть истории могла быть утрачена или подменена.")
    if book["broken_lines"]:
        lines.append(f"Битых строк пропущено честно: {book['broken_lines']}.")
    if not book["records"]:
        lines.append("Записей нет: по этой крови сказать нечего.")
        lines.append("")
        return "\n".join(lines)
    lines.append(f"Записей: {len(book['records'])}.")
    lines.append("")
    for record in book["records"]:
        lines.append(f"## {record['что']} — {record['кто инициировал']}")
        lines.append(f"- кто инициировал: {record['кто инициировал']}")
        lines.append(f"- когда случилось: {record['когда']}")
        lines.append(f"- результат: {record['результат']}")
        if "что не сделано" in record:
            lines.append(f"- что не сделано: {record['что не сделано']}")
        lines.append(f"- цена: {record['цена']}")
        lines.append(f"- можно ли отменить: {record['можно ли отменить']}")
        lines.append(f"- чем подтверждён: {record['чем подтверждён']}")
        lines.append("")
    lines.append("## Итог")
    totals = book["totals"]
    lines.append(f"- полная цена: токены {totals['tokens_in']}/{totals['tokens_out']}, {totals['seconds']:g} с")
    if book["plans_unfulfilled"]:
        lines.append(f"- планов без подтверждённого исполнения: {book['plans_unfulfilled']}")
    lines.append("- отмена действий не обещается: компенсатор не построен (W-0024)")
    lines.append("")
    return "\n".join(lines)
