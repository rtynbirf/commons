# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Творческая песочница — гипотезы тела, не факты (ТЗ-2.2, A20, SPEC-0001 п.9).

Творчество — часть тела, но факт и гипотеза — разные жанры крови. Гипотеза,
рождённая в песочнице, живёт в крови честно: тип reflect с `trust:
unverified` (заявка тела без независимых проверок — SPEC-0003 п.10) и
маркером «гипотеза, не факт» в payload (`sandbox: true`).

Гипотеза не имеет полномочий и не исполняется сама по себе: она может стать
шагом плана только через `Step.basis` + обязательный критерий приёмки
(`Step.accept`, W-0027) — цикл роняет шаг на гипотезе без проверки veto до
факта (гипотеза не становится фактом), а ссылку на гипотезу, которой в
крови нет, — тоже veto (незаявленное не достраивается, A02). Проверенный
путь честен: план несёт basis ДО факта, reflect называет критерий, которым
мерил, — гипотеза превратилась в проверенное действие, а не в молчаливую
веру.
"""

from __future__ import annotations

from typing import Any

from blood.envelope import Cost, make
from blood.journal import Journal

SANDBOX_NOTE = "гипотеза, не факт"


class Sandbox:
    """Песочница творчества: propose() пишет гипотезу в кровь, hypotheses() читает.

    Гипотеза — reflect-конверт с `trust: unverified`, `payload.sandbox: true`
    и заметкой «гипотеза, не факт». Полномочий у гипотезы нет: орган —
    `self` (думает тело, не орган), никаких fs/network/process грамматика не
    даёт — исполнение возможно только шагом цикла через страж полномочий
    (SPEC-0002), и то лишь с критерием проверки (SPEC-0001 п.9).
    """

    def __init__(self, journal: Journal) -> None:
        self._journal = journal

    def propose(self, text: str, *, basis: str | None = None) -> dict[str, Any]:
        """Рождает гипотезу: честная запись в кровь, ничего не исполняется.

        `basis` — id гипотезы-основания, если творчество наследует (честное
        происхождение, SPEC-0003 п.10). Пустой текст — ValueError: немой
        гипотезы не бывает.
        """
        if not isinstance(text, str) or not text.strip():
            raise ValueError("гипотеза без текста — не гипотеза")
        payload: dict[str, Any] = {"hypothesis": text, "sandbox": True, "note": SANDBOX_NOTE}
        if basis is not None:
            payload["basis"] = basis
        return self._journal.append(make(
            "reflect", "brainstem", "self", f"sandbox:{text[:16].strip()}",
            payload, Cost(0, 0, 0.0), trust="unverified",
        ))

    def hypotheses(self) -> list[dict[str, Any]]:
        """Все живые гипотезы этой крови (по факту конвертов, не по памяти)."""
        return [
            envelope
            for envelope in self._journal.all()
            if envelope.get("type") == "reflect"
            and isinstance(envelope.get("payload"), dict)
            and envelope["payload"].get("sandbox") is True
        ]

    def find(self, hyp_id: str) -> dict[str, Any] | None:
        """Гипотеза по id из крови; None — её там нет (незаявленное не строится)."""
        for envelope in self.hypotheses():
            if envelope["id"] == hyp_id:
                return envelope
        return None
