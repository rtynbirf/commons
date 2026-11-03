# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Правило тишины — одобрение с заявленным окном, по умолчанию «нет» (W-0032).

SPEC-0004 п.7 (поверх ADR-0006, волна №23): у тишины есть записанное окно и
поведение по умолчанию — необратимое действие, по которому одобрение не пришло
за окно, отменяется по-записанному (veto от правила, не от Человека), а не
ждёт вечно. Правило наружу уже работало (донорский триггер тишины —
`runs/2026-11-03-wave17-membrane-blood/donors-sweep.md`); здесь оно общее —
и внутрь дома.

Грамматика (ADR-0015):

- запрос — событие `approval.request` с ЗАЯВЛЕННЫМ окном (`window_seconds`),
  приоритетом из словаря внимания (W-0025) и вычисленным `expires_at`;
  запроса без окна не существует — окно ≤ 0 и чужой приоритет роняются
  ДО записи (fail-closed, ADR-0014), конверта нет — события нет;
- одобрение — `approval.grant` с `causation_id` запроса и `who` (строка-
  заявка, доверие unverified по природе — W-0024); ключ идемпотентности
  `approval.grant:{request_id}` — повторное одобрение не создаёт вторую
  строку (A01);
- ответ (`answer`) — по-записанному: одобрение до окна — `granted`;
  окно истекло без одобрения — правило само пишет `veto`
  (`approval.silence:{request_id}`, A01) — **по умолчанию «нет»**,
  необратимое не исполнено (A17); до окна — `waiting`, ничего не пишет;
- опоздавшее одобрение остаётся в крови вестью (append-only) — необратимое
  не оживляет;
- ожидание не останавливает дом: остановлено только само необратимое
  действие (инвариант 32 llms.txt — тишина внешнего слова не блокирует
  работу МЫ).

Время передаётся параметром `now` (RFC 3339 c Z); None — настоящее время
(`blood.envelope.now_utc`). Живой прогон и приёмки подают время явно —
правило не спит и не таймерит: решение всегда читается из крови.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from blood.envelope import Cost, make, now_utc
from blood.journal import Journal
from brainstem.attention import attention_cost

GRANTED = "granted"
CANCELLED_BY_SILENCE = "cancelled_by_silence"
WAITING = "waiting"

_REQUEST = "approval.request"
_GRANT = "approval.grant"


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _fact_ts(envelope: dict[str, Any]) -> str:
    """Время факта события (честное происхождение, SPEC-0003 п.10): заявленное
    occurred_at, незаявленное — момент записи. Правило сравнивает факты, а не
    бумагу: injected-время живого прогона живёт в occurred_at."""
    return envelope.get("occurred_at") or envelope["ts"]


def _fmt(moment: datetime) -> str:
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _resolve_now(now: str | None) -> datetime:
    return _parse(now) if now is not None else _parse(now_utc())


def request(
    journal: Journal,
    *,
    what: str,
    window_seconds: int,
    priority: str,
    trace_id: str,
    organ: str = "self",
    tool: str | None = None,
    question: str | None = None,
    idempotency_key: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Пишет запрос одобрения Человеку — событие `approval.request` (SPEC-0004 п.7).

    Окно заявлено просящим: `window_seconds` — целое > 0; запроса без окна
    не существует (ValueError до записи, ADR-0014). Приоритет — из словаря
    внимания W-0025 (`brainstem.attention.ATTENTION_PRIORITIES`); расход
    внимания заявляется ценой события (`cost.attention` — P0/P1 = 1).
    Повторная заявка того же намерения (тот же трейс и `what`) возвращает
    уже записанный конверт — вторая строка не создаётся (A01, ключ
    `approval.request:{trace_id}:{what}`, если ключ не передан явно).
    """
    if window_seconds is None or int(window_seconds) <= 0:
        raise ValueError(
            f"окно тишины должно быть целым > 0, получено {window_seconds!r} — запроса без окна не существует (SPEC-0004 п.7, ADR-0014)"
        )
    price = attention_cost(priority)  # чужой приоритет — fail-closed до записи
    moment = _resolve_now(now)
    expires_at = _fmt(moment + timedelta(seconds=int(window_seconds)))
    payload: dict[str, Any] = {
        "what": what,
        "window_seconds": int(window_seconds),
        "priority": priority,
        "expires_at": expires_at,
    }
    if tool is not None:
        payload["tool"] = tool
    if question is not None:
        payload["question"] = question
    return journal.append(
        make(
            _REQUEST,
            "pid1",
            organ,
            trace_id,
            payload,
            Cost(attention=price),
            idempotency_key=idempotency_key or f"approval.request:{trace_id}:{what}",
            occurred_at=_fmt(moment),
            trust="unverified",
        )
    )


def grant(
    journal: Journal,
    ask: dict[str, Any],
    *,
    who: str,
    trace_id: str,
    note: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Пишет одобрение Человека — `approval.grant` с причинной связью на запрос.

    `who` — строка-заявка («PID 1, 2026-11-03»), доверие unverified по
    природе (W-0024). Повторное одобрение того же запроса возвращает уже
    записанный конверт — вторая строка не создаётся (A01, ключ
    `approval.grant:{request_id}`). Опоздавшее одобрение тоже записывается:
    кровь append-only помнит всё — исполнить необратимое оно не оживляет
    (решает `answer`).
    """
    moment = _resolve_now(now)
    payload: dict[str, Any] = {"request_id": ask["id"], "who": who}
    if note is not None:
        payload["note"] = note
    return journal.append(
        make(
            _GRANT,
            "pid1",
            ask.get("organ", "self"),
            trace_id,
            payload,
            Cost(),
            idempotency_key=f"approval.grant:{ask['id']}",
            causation_id=ask["id"],  # честное происхождение (SPEC-0003 п.10)
            occurred_at=_fmt(moment),
            trust="unverified",
        )
    )


def _grant_for(journal: Journal, request_id: str) -> dict[str, Any] | None:
    """Одобрение запроса: первое по крови; повторные — дедуп (A01, тот же ключ)."""
    for envelope in journal.by_type(_GRANT):
        if (envelope.get("payload") or {}).get("request_id") == request_id:
            return envelope
    return None


def _silence_veto_for(journal: Journal, request_id: str) -> dict[str, Any] | None:
    for envelope in journal.by_type("veto"):
        payload = envelope.get("payload") or {}
        if payload.get("request_id") == request_id and payload.get("rule") == "silence":
            return envelope
    return None


def answer(
    journal: Journal,
    ask: dict[str, Any],
    *,
    now: str | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Ответ на запрос одобрения — по-записанному (SPEC-0004 п.7).

    Возвращает (вердикт, конверт ответа):

    - `cancelled_by_silence` — правило уже отменило (veto записан): решение
      самого правила — тоже кровь, повторное решение возвращает ту же строку
      (A01); опоздавшее одобрение решение не переворачивает — пере-спросить
      можно новой заявкой, необратимое оживлять нечем;
    - `granted` — одобрение записано, его ВРЕМЯ ФАКТА до `expires_at`
      (правило сравнивает факты, не бумагу — SPEC-0003 п.10);
    - `waiting` — окно ещё не истекло, одобрения нет: ожидание ничего
      не пишет и ничего не отменяет.

    Окно истекло без одобрения — правило тишины само пишет `veto`
    (source `pid1`, причина «правило тишины…», ключ
    `approval.silence:{request_id}`, A01) — **по умолчанию «нет»**,
    необратимое не исполнено (A17).
    """
    request_id = ask["id"]
    payload = ask.get("payload") or {}
    expires_at = payload["expires_at"]
    moment = _resolve_now(now)

    cancelled = _silence_veto_for(journal, request_id)
    if cancelled is not None:
        return CANCELLED_BY_SILENCE, cancelled

    given = _grant_for(journal, request_id)
    if given is not None and _parse(_fact_ts(given)) <= _parse(expires_at):
        return GRANTED, given

    if moment < _parse(expires_at):
        return WAITING, None

    veto = journal.append(
        make(
            "veto",
            "pid1",
            ask.get("organ", "self"),
            ask["trace_id"],
            {
                "reason": f"правило тишины: окно истекло {expires_at} без одобрения — по умолчанию «нет» (W-0032, SPEC-0004 п.7)",
                "request_id": request_id,
                "rule": "silence",
                "priority": payload.get("priority"),
                "what": payload.get("what"),
            },
            Cost(),
            idempotency_key=f"approval.silence:{request_id}",
            causation_id=request_id,
            occurred_at=_fmt(moment),
            trust="verified",  # правило видело само: истечение окна — факт крови
        )
    )
    return CANCELLED_BY_SILENCE, veto


def pending(journal: Journal, *, now: str | None = None) -> list[dict[str, Any]]:
    """Запросы без ответа и с живым окном: одобрения нет, тишина ещё не наступила."""
    moment = _resolve_now(now)
    left: list[dict[str, Any]] = []
    for ask in journal.by_type(_REQUEST):
        request_id = ask["id"]
        if _silence_veto_for(journal, request_id) is not None:
            continue  # правило уже отменило — решён
        given = _grant_for(journal, request_id)
        if given is not None and _parse(_fact_ts(given)) <= _parse((ask.get("payload") or {})["expires_at"]):
            continue  # одобрено — решён
        if moment >= _parse((ask.get("payload") or {})["expires_at"]):
            continue  # окно истекло — запрос уже отменён правилом (решает answer)
        left.append(ask)
    return left
