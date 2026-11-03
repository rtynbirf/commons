"""Оценка пути — процессная проекция крови (W-0020).

SPEC-0003 п.18 (Ф-2.7 ТЗ ревизора, волна №26): конверт уже несёт цену события
(п.3) и цену внимания Человека (п.17), но оценка ПУТИ жила только в исходе —
`run() = True` прячет путь, которым он получен. Зерно PRM коллеги: шаг,
переживший отказ и восстановленный, стоит иначе, чем гладкий путь, — и это
обязано быть названо, а не спрятано за молчаливой удачей.

Честные правила:

- проекция read-only, как дневник (п.12) и выжимка (п.13): кровь не трогает;
- только измеримое: планы, шаги (акты), провалы (veto/halt/error/security.violation
  — словарь счётчика отказов W-0021, копий нет), переигрки (акт после провала
  того же трейса), вопросы Человеку (оба диалекта approval, п.17), компенсации
  (планы, несущие `act_id` —笔 compensator, SPEC-0001 п.6);
- исход трейса: последний конверт `reflect`/`halt` — назван; иначе «открыт» —
  открытый трейс не приукрашается (A05: план ≠ факт);
- «восстановлен» — честное слово: провалы были, исход — не halt; провал без
  восстановления не хвалится;
- без хваления (дух W-0021): рендер называет факты пути, слово «успешно»
  не пишет вовсе — «успешно» без проверки не пишется и здесь.
"""

from __future__ import annotations

from typing import Any

from blood.refusals import REFUSAL_TYPES

APPROVAL_DIALECTS = ("approval.request", "approval.requested")


def path_of(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Оценка пути одного трейса по его конвертам (по порядку файла).

    Принимает список конвертов одного `trace_id`; ничего не пишет.
    """
    plans = 0
    acts = 0
    failures = 0
    interruptions = 0
    compensations = 0
    retries = 0
    retry_pending = False
    for event in events:
        if not isinstance(event, dict):
            continue
        etype = event.get("type")
        payload = event.get("payload") or {}
        if etype == "plan":
            plans += 1
            if payload.get("act_id"):
                compensations += 1
        elif etype == "act":
            acts += 1
            if retry_pending:
                retries += 1
                retry_pending = False
        elif etype in REFUSAL_TYPES:
            failures += 1
            retry_pending = True
        elif etype in APPROVAL_DIALECTS:
            interruptions += 1
    last = events[-1].get("type") if events else None
    outcome = last if last in ("reflect", "halt") else "open"
    recovered = failures > 0 and outcome != "halt"
    smooth = failures == 0 and retries == 0 and compensations == 0
    return {
        "plans": plans,
        "acts": acts,
        "failures": failures,
        "retries": retries,
        "interruptions": interruptions,
        "compensations": compensations,
        "outcome": outcome,
        "recovered": recovered,
        "smooth": smooth,
    }


def render(path: dict[str, Any]) -> str:
    """Путь человеческим языком: факты, без хваления («успешно» не пишется)."""
    outcome_words = {
        "reflect": "исход — рефлексия записана",
        "halt": "исход — остановлен (halt)",
        "open": "исхода нет — трейс открыт",
    }
    parts = [
        f"шагов {path['acts']}",
        f"планов {path['plans']}",
        f"провалов {path['failures']}",
        f"переигрок {path['retries']}",
        f"вопросов Человеку {path['interruptions']}",
        f"компенсаций {path['compensations']}",
        outcome_words.get(path["outcome"], "исход не назван"),
    ]
    if path["recovered"]:
        parts.append(f"путь пережил {path['failures']} провалов и был восстановлен")
    elif path["smooth"]:
        parts.append("путь без провалов")
    elif path["outcome"] == "halt":
        parts.append("провал не восстановлен — остановлен")
    return "Путь: " + ", ".join(parts) + "."
