# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Бюджет внимания человека — человеческий контур поверх дома (W-0025).

SPEC-0004 п.8 (зерно FR-09 пакета «Human Membrane», волна №23): внимание
Человека — ресурс организма. Словарь приоритетов один — здесь (копий нет):

- **P0** — остановка перед риском/необратимостью: спрашивает всегда — у риска
  нет безопасного default (W-0024: необратимое без одобрения не исполняется);
- **P1** — срочное существенное решение: спрашивает, только если нет
  безопасного default;
- **P2** — дневная сводка: не прерывает (выжимка крови — W-0019);
- **P3** — тихая запись: не прерывает.

Косметические вопросы не задаются: вопрос с безопасным default, который можно
изменить позже, не задаётся — запись вместо вопроса (SPEC-0004 п.8).

Цена внимания — `cost.attention` (SPEC-0003 п.17): прерывание (P0/P1) — 1,
сводка и тихая запись — 0; ноль не пишется (старый стиль крови жив, A02).

**Скрытой поведенческой телеметрии нет и не будет**: этот модуль ничего
не измеряет у Человека и ничего не запрашивает сам — он только переводит
заявленную кровь в счёт и слова. Неизмеримое = UNKNOWN (None), не ноль.
«Меньше вопросов не значит лучше, если растут опасные действия»: метрики
показывают вопросы и необратимые действия рядом — оборотную сторону не прячут.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

# Словарь приоритетов внимания (SPEC-0004 п.8) — единственный, копий нет.
ATTENTION_PRIORITIES: tuple[str, ...] = ("P0", "P1", "P2", "P3")

PRIORITY_MEANING: dict[str, str] = {
    "P0": "остановка перед риском/необратимостью — спрашивает всегда",
    "P1": "срочное существенное решение — спрашивает без безопасного default",
    "P2": "дневная сводка — не прерывает",
    "P3": "тихая запись — не прерывает",
}

# Прерывания (P0/P1) тратят внимание Человека; сводка и тихая запись — нет.
_INTERRUPTING = ("P0", "P1")


def attention_cost(priority: str) -> int:
    """Заявленный расход внимания Человека (SPEC-0003 п.17): P0/P1 — 1, P2/P3 — 0.

    Приоритет не из словаря — fail-closed (ValueError до факта, ADR-0014):
    опечатка не значит молча «не прерывает».
    """
    if priority not in ATTENTION_PRIORITIES:
        raise ValueError(
            f"приоритет внимания не понимается: {priority!r} — словарь {ATTENTION_PRIORITIES}"
        )
    return 1 if priority in _INTERRUPTING else 0


def should_ask(priority: str, *, safe_default: bool) -> tuple[bool, str]:
    """Задавать ли Человеку вопрос (политика P0–P3, SPEC-0004 п.8).

    Возвращает (решение, причина словами). P0 — всегда да (у риска нет
    безопасного default); P1 — да, только если безопасного default нет
    (косметический вопрос с безопасным default не задаётся); P2/P3 — нет:
    сводка и тихая запись прерываний не создают. Неизвестный приоритет —
    fail-closed (через attention_cost, ADR-0014).
    """
    attention_cost(priority)  # словарь проверяет один — здесь (копий нет)
    if priority == "P0":
        return True, f"{priority}: {PRIORITY_MEANING[priority]} — безопасного default у риска нет"
    if priority == "P1":
        if safe_default:
            return (
                False,
                f"{priority}: есть безопасный default, который можно изменить позже — косметический вопрос не задаётся",
            )
        return True, f"{priority}: {PRIORITY_MEANING[priority]} — безопасного default нет"
    return False, f"{priority}: {PRIORITY_MEANING[priority]} — прерывания нет"


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _fact_ts(envelope: dict[str, Any]) -> str:
    """Время факта (SPEC-0003 п.10): заявленное occurred_at, незаявленное — запись."""
    return envelope.get("occurred_at") or envelope["ts"]


def metrics(events: Any, *, now: str | None = None) -> dict[str, Any]:
    """Счёт внимания по заявленной крови — read-only проекция (SPEC-0004 п.9).

    Принимает только конверты крови (какие дали — те и считает: ни файлов,
    ни сети, ни скрытого состояния — телеметрии нет). Неизмеримое = UNKNOWN
    (None), не ноль. Читает оба диалекта крови одобрения (стык 0.42.1):
    живой контур `brainstem/silence.py` пишет `approval.requested` →
    `approval.granted`/`approval.veto`/`approval.expired`, кровь волны №23
    нашей линии — `approval.request`/`approval.grant` + `veto` с
    `request_id` (валидна навсегда — гематология); ни один вопрос не
    считается дважды — диалекты не смешиваются внутри контура.

    Ключи:

    - `questions` — вопросы Человеку (`approval.request` + `approval.requested`);
    - `interruptions` — из них прерывания (заявленный `cost.attention` > 0);
      вопрос без заявленной цены — не прерывание в счёте (незаявленное не
      достраивается, A02), но вопросом остаётся;
    - `granted` / `refused` / `cancelled_by_silence` — ответы (одобрение;
      явный отказ Человека — veto с request_id без правила или
      `approval.veto`; отказ правилом тишины — veto с rule=silence или
      `approval.expired`);
    - `late_approvals` — одобрения, записанные после отмены тишиной: весть
      в крови (append-only), решение приняла тишина — отдельным счётом,
      не спрятаны и не перепутаны с решениями; связка одобрения с запросом
      заявлена только в диалекте `approval.grant` (request_id) — в контуре
      одобрение после `expired` невозможно (контур одноразовый), счёт — 0;
    - `wait_seconds_max` — максимальное ожидание ответа: заявленное
      `waited_s` контура, у нашей крови — разница времён факта
      (запись вопроса → запись ответа); не считалось — None;
    - `dismissed_fraction` — доля отказов (тишина + явное «нет») среди
      решённых вопросов; решённых нет — None;
    - `dangerous_actions` — необратимые действия рядом с вопросами:
      «меньше вопросов не значит лучше, если растут опасные действия».

    Чистая функция: та же кровь — тот же отчёт.
    """
    items = list(events)
    questions_our = [e for e in items if e.get("type") == "approval.request"]
    questions_their = [e for e in items if e.get("type") == "approval.requested"]
    questions = questions_our + questions_their
    interruptions = [e for e in questions if int((e.get("cost") or {}).get("attention", 0)) > 0]

    grants: dict[str, dict[str, Any]] = {}
    refusals: dict[str, dict[str, Any]] = {}
    silences: dict[str, dict[str, Any]] = {}
    for e in items:
        if e.get("type") == "approval.grant":
            rid = (e.get("payload") or {}).get("request_id")
            if isinstance(rid, str):
                grants.setdefault(rid, e)  # A01: повтор ключа не создаёт вторую строку
        elif e.get("type") == "veto":
            payload = e.get("payload") or {}
            rid = payload.get("request_id")
            if isinstance(rid, str):
                if payload.get("rule") == "silence":
                    silences.setdefault(rid, e)
                else:
                    refusals.setdefault(rid, e)

    # Диалект контура: ответы без request_id — корреляция по (trace_id, what);
    # контур одноразовый — первое решение и есть единственное.
    their_granted = [e for e in items if e.get("type") == "approval.granted"]
    their_veto = [e for e in items if e.get("type") == "approval.veto"]
    their_expired = [e for e in items if e.get("type") == "approval.expired"]
    their_answers: dict[tuple[Any, Any], dict[str, Any]] = {}
    for e in (*their_granted, *their_veto, *their_expired):
        payload = e.get("payload") or {}
        their_answers.setdefault((e.get("trace_id"), payload.get("what")), e)

    waits: list[float] = []
    late_approvals = 0
    granted_our = 0
    for rid, envelope in grants.items():
        if rid in silences:
            late_approvals += 1  # опоздавшее одобрение — весть, решение приняла тишина (W-0032)
        else:
            granted_our += 1
    for question in questions_our:
        rid = question["id"]
        answer_event = (grants.get(rid) if rid not in silences else None) or refusals.get(rid) or silences.get(rid)
        if answer_event is not None:
            waits.append((_parse(_fact_ts(answer_event)) - _parse(_fact_ts(question))).total_seconds())
    for question in questions_their:
        payload = question.get("payload") or {}
        answer_event = their_answers.get((question.get("trace_id"), payload.get("what")))
        if answer_event is not None:
            waited = (answer_event.get("payload") or {}).get("waited_s")
            # ожидание заявлено контуром (waited_s) — заявленное честнее вычисленного
            waits.append(float(waited) if isinstance(waited, (int, float))
                         else (_parse(_fact_ts(answer_event)) - _parse(_fact_ts(question))).total_seconds())

    granted = granted_our + len(their_granted)
    refused = len(refusals) + len(their_veto)
    silenced = len(silences) + len(their_expired)
    decided = granted + refused + silenced
    denied = refused + silenced
    return {
        "questions": len(questions),
        "interruptions": len(interruptions),
        "granted": granted,
        "refused": refused,
        "cancelled_by_silence": silenced,
        "late_approvals": late_approvals,
        "wait_seconds_max": round(max(waits), 6) if waits else None,
        "dismissed_fraction": round(denied / decided, 6) if decided else None,
        "dangerous_actions": sum(
            1
            for e in items
            if e.get("type") == "act" and (e.get("payload") or {}).get("reversibility") == "irreversible"
        ),
    }
