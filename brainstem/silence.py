"""Правило тишины — W-0032 (SPEC-0004 v0.2.0 п.8): у тишины есть окно и дефолт.

Необратимое действие, по которому одобрение Человека не пришло за окно,
отменяется по-записанному: тишина = «нет» (G7). Весь контур одобрения
виден в крови: approval.requested → approval.granted | approval.veto |
approval.expired — ни одного немого ожидания. Правило симметрично
донорскому триггеру тишины (окно follow-up наружу), но работает внутрь
дома. Ответ Человека пишется с источником pid1 — воля человека в крови
отличима от воли тела. Вопрос с окном — потраченное внимание Человека:
approval.requested несёт cost.attention = 1 с классом P0 (W-0025,
SPEC-0003 п.17, SPEC-0004 п.9) — тело видит, сколько внимания попросило.

Fail-closed: окно <= 0 — ValueError ДО первой записи (правило без окна —
не правило, ничего не случилось); канал упал или вернул мусор — error-
конверт (назван один раз) и молчание до конца окна.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from blood.envelope import Cost, make
from blood.journal import Journal

ANSWER_APPROVED = "approved"
ANSWER_VETOED = "vetoed"
ANSWER_EXPIRED = "expired"

# Ответы, которые канал одобрения имеет право давать; всё прочее — мусор.
_ANSWERS = (ANSWER_APPROVED, ANSWER_VETOED)


@dataclass(frozen=True)
class ApprovalRequest:
    """Просьба об одобрении (W-0032): что, окно, зачем.

    Окно обязано: правило без окна — не правило (SPEC-0004 п.8), проверка
    до первой записи в кровь.
    """

    what: str
    window_s: float
    why: str = ""


def await_approval(
    journal: Journal,
    trace_id: str,
    request: ApprovalRequest,
    channel: Callable[[dict[str, Any]], str | None],
    *,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    poll_interval: float = 0.05,
) -> str:
    """Правило тишины: окно → ответ Человека → дефолт по-записанному.

    Пишет `approval.requested`, опрашивает канал до конца окна и завершает
    контур: `approval.granted` / `approval.veto` (ответ Человека, source
    pid1) или `approval.expired` (тишина, source brainstem). Возвращает
    "approved" | "vetoed" | "expired".

    Канал получает словарь {what, why, seconds_left} и отвечает
    "approved" / "vetoed" / None. Сломанный канал (исключение) называется
    одним error-конвертом и дальше считается тишиной; мусорный ответ
    называется error-конвертом и трактуется как молчание — fail-closed.
    """
    if request.window_s <= 0:
        raise ValueError(
            f"правило тишины без окна — не правило (SPEC-0004 п.8): window_s={request.window_s}"
        )
    if poll_interval <= 0:
        raise ValueError(f"poll_interval должен быть > 0: {poll_interval}")

    journal.append(make(
        "approval.requested", "brainstem", "self", trace_id,
        {
            "what": request.what,
            "why": request.why,
            "window_s": request.window_s,
            "default": "cancel",
            "rule": "silence=no (W-0032, SPEC-0004 п.8)",
        },
        Cost(attention=1),
        attention_class="P0",
    ))

    started = clock()
    deadline = started + request.window_s
    channel_name = getattr(channel, "__name__", "callable")
    anomaly_named = False  # сломанный/мусорный канал называется один раз — кровь не засоряем
    while True:
        left = deadline - clock()
        if left <= 0:
            break
        try:
            answer = channel({"what": request.what, "why": request.why, "seconds_left": round(left, 6)})
        except Exception as exc:  # noqa: BLE001 — сломанный канал не отменяет правило
            if not anomaly_named:
                journal.append(make(
                    "error", "brainstem", "self", trace_id,
                    {"reason": f"канал одобрения упал: {exc!r}", "what": request.what},
                ))
                anomaly_named = True
            answer = None
        if answer in _ANSWERS:
            waited = round(clock() - started, 6)
            kind = "approval.granted" if answer == ANSWER_APPROVED else "approval.veto"
            journal.append(make(
                kind, "pid1", "self", trace_id,
                {
                    "what": request.what,
                    "answer": answer,
                    "waited_s": waited,
                    "channel": channel_name,
                },
            ))
            return answer
        if answer is not None:
            if not anomaly_named:
                journal.append(make(
                    "error", "brainstem", "self", trace_id,
                    {"reason": f"канал одобрения вернул мусор: {answer!r}", "what": request.what},
                ))
                anomaly_named = True
        sleeper(min(poll_interval, max(left, 0.0)))

    journal.append(make(
        "approval.expired", "brainstem", "self", trace_id,
        {
            "what": request.what,
            "window_s": request.window_s,
            "waited_s": round(clock() - started, 6),
            "default": "cancel",
            "reason": "silence",
        },
    ))
    return ANSWER_EXPIRED
