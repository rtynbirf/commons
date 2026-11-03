# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Контур доставки поручений — ТЗ-2.4 (A24/A25, SPEC-0001 п.10, волна №29).

Дух ADR-001 пакета «Human Membrane» (зерно принято разбором, инвариант 24):
кровь — журнал фактов, а не шина pub/sub. Dispatcher не широковещает: он
доставляет поручение обработчику и пишет в кровь факты доставки —
попытки, вердикты, мёртвые письма. Грамматика вердиктов одна:

- `DONE` — доставлено, ответ обработчика возвращён;
- `RETRY(n)` — попытка n не прошла (n < max_attempts), отказ назван в крови
  (error-конверт) и доставка продолжается;
- `DLQ` — attempts исчерпаны: мёртвое письмо названо в крови поимённо
  (label, причина, число попыток) — полуготовность не выдаётся за успех;
  исключение наружу не вырывается (перегрузка без каскада);
- `SHED` — переполнение очереди: новое поручение честно отвергнуто ДО
  факта, уже принятые договаривают (перегрузка без каскада);
- `TIMEOUT` — поручение превысило дедлайн: эффект мог случиться — назван
  честно (граница как у аварийного стопа, SPEC-0001 п.8), вердикт в крови.

Повторная доставка идемпотентна (A01): тот же `key` возвращает записанный
исход, обработчик не вызывается второй раз — повтор не повторяет эффект.
Таймаут и границы очереди — данные конструктора (G2), не код.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from blood.envelope import Cost, make
from blood.journal import Journal

DONE = "DONE"
RETRY = "RETRY"
DLQ = "DLQ"
SHED = "SHED"
TIMEOUT = "TIMEOUT"

VERDICTS = (DONE, RETRY, DLQ, SHED, TIMEOUT)


class Dispatcher:
    """Доставка поручений без каскада: очередь ограничена, отказ назван, повтор — тот же исход.

    `max_queue` — предел одновременно живых поручений (A25: concurrency);
    `max_attempts` — предел попыток до DLQ; `timeout` — дедлайн поручения
    в секундах (A25: timeout); `clock`/`sleeper` — инъекция времени (приёмки
    не спят). Каждая попытка и каждый вердикт — факты в крови.
    """

    def __init__(
        self,
        journal: Journal,
        *,
        max_queue: int = 8,
        max_attempts: int = 3,
        timeout: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_queue < 1 or max_attempts < 1:
            raise ValueError("очередь и попытки без предела — не доставка, а надежда")
        if timeout <= 0:
            raise ValueError("дедлайн <= 0 — не дедлайн")
        self._journal = journal
        self._max_queue = max_queue
        self._max_attempts = max_attempts
        self._timeout = timeout
        self._clock = clock
        self._sleeper = sleeper
        self._inflight: dict[str, str] = {}  # key → label (живые поручения)
        self._resolved: dict[str, dict[str, Any]] = {}  # key → исход (A01)

    # --- публичный глагол ------------------------------------------------------

    def deliver(self, key: str, action: Callable[[], Any], *, label: str) -> dict[str, Any]:
        """Доставляет поручение обработчику; кровь получает факты, наружу — вердикт.

        Идемпотентность (A01): поручение с уже известным `key` не вызывает
        обработчик второй раз — возвращается записанный исход с
        `redelivered: true`.
        """
        if not isinstance(key, str) or not key:
            raise ValueError("поручение без ключа не идемпотентно — доставки не будет")
        if key in self._resolved:
            return {**self._resolved[key], "redelivered": True}
        if key in self._inflight:
            return {"key": key, "label": label, "verdict": SHED,
                    "reason": "поручение уже в работе — повтор до завершения не принимается",
                    "attempts": 0, "redelivered": False}

        if len(self._inflight) >= self._max_queue:
            self._journal.append(make(
                "alert", "brainstem", "self", f"dispatch:{key}",
                {"reason": f"очередь доставки полна ({self._max_queue}) — поручение {label!r} отвергнуто до факта",
                 "delivery": {"key": key, "label": label, "verdict": SHED}},
                Cost(0, 0, 0.0),
            ))
            return {"key": key, "label": label, "verdict": SHED,
                    "reason": f"очередь полна ({self._max_queue}) — перегрузка названа, каскада нет",
                    "attempts": 0, "redelivered": False}

        self._inflight[key] = label
        try:
            return self._run(key, action, label)
        finally:
            self._inflight.pop(key, None)

    # --- внутренняя доставка -----------------------------------------------------

    def _run(self, key: str, action: Callable[[], Any], label: str) -> dict[str, Any]:
        last_reason = ""
        for attempt in range(1, self._max_attempts + 1):
            started = self._clock()
            try:
                result = action()
            except Exception as exc:  # noqa: BLE001 — отказ назван, каскада нет
                last_reason = repr(exc)[:160]
                self._journal.append(make(
                    "error", "brainstem", "self", f"dispatch:{key}",
                    {"reason": f"попытка {attempt}/{self._max_attempts} не прошла: {last_reason}",
                     "delivery": {"key": key, "label": label, "verdict": RETRY, "attempt": attempt}},
                    Cost(0, 0, 0.0),
                ))
                verdict = RETRY
                if attempt < self._max_attempts:
                    self._journal.append(make(
                        "act", "brainstem", "self", f"dispatch:{key}",
                        {"delivery": {"key": key, "label": label, "verdict": RETRY,
                                      "attempt": attempt, "next": attempt + 1},
                         "path": [{"stage": f"attempt-{attempt}", "verdict": "failed", "note": last_reason},
                                  {"stage": "retry", "verdict": "scheduled", "note": f"попытка {attempt + 1} назначена"}]},
                        Cost(0, 0, 0.0),
                    ))
                    self._sleeper(0.0)  # такт между попытками (инъекция времени)
                    continue
            else:
                elapsed = self._clock() - started
                if elapsed > self._timeout:
                    # Дедлайн превышен: эффект мог случиться — назван честно
                    # (граница как у аварийного стопа SPEC-0001 п.8), результат
                    # не выдаётся за доставленный вовремя.
                    self._journal.append(make(
                        "error", "brainstem", "self", f"dispatch:{key}",
                        {"reason": f"поручение {label!r} превысило дедлайн {self._timeout}s (факт {elapsed:.3f}s) — результат не принят",
                         "delivery": {"key": key, "label": label, "verdict": TIMEOUT, "attempt": attempt}},
                        Cost(0, 0, 0.0),
                    ))
                    outcome = {"key": key, "label": label, "verdict": TIMEOUT,
                               "reason": f"дедлайн {self._timeout}s превышен ({elapsed:.3f}s) — эффект назван, результат не принят",
                               "attempts": attempt, "redelivered": False}
                    self._resolved[key] = outcome
                    return outcome
                self._journal.append(make(
                    "act", "brainstem", "self", f"dispatch:{key}",
                    {"delivery": {"key": key, "label": label, "verdict": DONE, "attempt": attempt},
                     "path": [{"stage": f"attempt-{attempt}", "verdict": "ok"}]},
                    Cost(0, 0, 0.0),
                ))
                outcome = {"key": key, "label": label, "verdict": DONE,
                           "result": result, "attempts": attempt, "redelivered": False}
                self._resolved[key] = outcome
                return outcome

        # попытки исчерпаны — мёртвое письмо названо поимённо (полуготовность
        # не выдаётся за успех), наружу ничего не вырывается (без каскада)
        self._journal.append(make(
            "error", "brainstem", "self", f"dispatch:{key}",
            {"reason": f"поручение {label!r} доставлено в DLQ: попыток {self._max_attempts}, последняя причина: {last_reason}",
             "delivery": {"key": key, "label": label, "verdict": DLQ, "attempts": self._max_attempts}},
            Cost(0, 0, 0.0),
        ))
        outcome = {"key": key, "label": label, "verdict": DLQ,
                   "reason": last_reason, "attempts": self._max_attempts, "redelivered": False}
        self._resolved[key] = outcome
        return outcome

    # --- чтение -------------------------------------------------------------------

    def dead_letters(self) -> list[dict[str, Any]]:
        """Мёртвые письма сессии — поимённо (кровь — истина, память — кэш)."""
        return [
            envelope
            for envelope in self._journal.all()
            if envelope.get("type") == "error"
            and isinstance(envelope.get("payload"), dict)
            and isinstance(envelope["payload"].get("delivery"), dict)
            and envelope["payload"]["delivery"].get("verdict") == DLQ
        ]
