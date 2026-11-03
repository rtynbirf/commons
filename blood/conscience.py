# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Совесть — read-проекция крови, сверяющая заявление тела с фактом (ТЗ-2.1, A19).

Зерно «совести» коллеги-LLM (docs/colleague-synthesis.md п.9, W-0021):
честный отказ — данные, а не стыд. Совесть продолжает тот же закон:
заявление о состоянии дома сверяется со счётчиком провалов живой крови
(`blood.refusals.count_refusals`, W-0021). На ложной посылке совесть не
поддакивает: расхождение названо поимённо (какое число, какие типы, какие
трейсы расходятся). Грамматика посылки fail-closed: незаявленное в посылке
не достраивается (A02) — чужой ключ роняется ValueError до всякой сверки.

Совесть — проекция чтения: кровь она не пишет (тот же жанр, что дневник
п.12 и выжимка п.13 SPEC-0003). Согласие всегда с доказательством, а не
просто «да»: facts несут живой замер счётчика.
"""

from __future__ import annotations

from typing import Any, Union

from blood.journal import Journal
from blood.refusals import count_refusals

# Грамматика посылки (fail-closed): только заявления, которые кровь может
# проверить по факту счётчика. Незаявленное не достраивается (A02).
PREMISE_KEYS = ("refusals", "refusal_types", "traces_failed")


def calibrate(premise: dict[str, Any], source: Union[Journal, str, "Path"]) -> dict[str, Any]:
    """Сверяет посылку тела с фактом провалов крови (A19, SPEC-0003 п.20).

    Посылка — заявление о провалах дома: `refusals` (заявленное число
    отказов), `refusal_types` (заявленные как все встретившиеся типы),
    `traces_failed` (заявленные как единственные провальные трейсы).
    Чужой ключ, не-целое число или не-список строк — ValueError до всякой
    сверки (незаявленное не достраивается). Возвращает честный вердикт:

    - `agree` — посылка сходится с кровью;
    - `disagreements` — поимённые расхождения (на ложной посылке пусто не бывает);
    - `facts` — живой замер счётчика W-0021 (доказательство, не мнение);
    - `words` — человеческий вердикт для дневника/Человека.
    """
    if not isinstance(premise, dict):
        raise ValueError(f"посылка — словарь заявлений, получено {type(premise).__name__}")
    unknown = sorted(set(premise) - set(PREMISE_KEYS))
    if unknown:
        raise ValueError(
            f"посылка говорит не то, что кровь может проверить: {', '.join(unknown)}; "
            f"грамматика посылки: {', '.join(PREMISE_KEYS)}"
        )
    if "refusals" in premise and not isinstance(premise["refusals"], int) or isinstance(premise.get("refusals"), bool):
        raise ValueError("посылка refusals — целое число отказов, не «настроение»")
    for key in ("refusal_types", "traces_failed"):
        if key in premise and (
            not isinstance(premise[key], list) or not all(isinstance(item, str) for item in premise[key])
        ):
            raise ValueError(f"посылка {key} — список строк")

    facts = count_refusals(source)
    disagreements: list[str] = []

    if "refusals" in premise and premise["refusals"] != facts["total"]:
        disagreements.append(
            f"заявлено отказов {premise['refusals']}, кровь говорит {facts['total']}"
        )
    if "refusal_types" in premise:
        claimed = set(premise["refusal_types"])
        real = set(facts["by_type"])
        if claimed != real:
            disagreements.append(
                f"типы отказов расходятся: в крови {sorted(real)}, заявлено {sorted(claimed)}"
            )
    if "traces_failed" in premise:
        claimed_traces = set(premise["traces_failed"])
        real_traces = set(facts["traces"])
        missed = sorted(real_traces - claimed_traces)
        invented = sorted(claimed_traces - real_traces)
        if missed:
            disagreements.append(f"провальные трейсы, которых посылка не назвала: {', '.join(missed)}")
        if invented:
            disagreements.append(f"трейсы, названные провальными, но в крови целые: {', '.join(invented)}")

    agree = not disagreements
    by_type = ", ".join(f"{name}×{count}" for name, count in sorted(facts["by_type"].items())) or "нет"
    if agree:
        words = f"Согласен: кровь подтверждает — провалов {facts['total']} ({by_type})."
    else:
        words = f"Не согласен: заявление расходится с кровью (провалов {facts['total']}: {by_type}) — " + "; ".join(disagreements) + "."
    return {
        "agree": agree,
        "premise": premise,
        "facts": {
            "total": facts["total"],
            "by_type": dict(facts["by_type"]),
            "traces": sorted(facts["traces"]),
            "skipped": facts.get("skipped", 0),
        },
        "disagreements": disagreements,
        "words": words,
    }
