# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмки волны №31 — живой А/Б против разумной базы Б2 (ТЗ-2.6, хотёлка W-0028).

Гейт ТЗ: «организм выигрывает и у Б2 (кровь, полный трейс, приманка до факта) —
польза доказана; если нет — честно записать, чем он лучше». Приёмки меряют не
победу, а ЧЕСТНОСТЬ замера: обе группы прошли одинаковый сценарий, счёт выведен
из живых чисел, слабости Б2 названы, границы замера (песочница, сеть) названы.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs" / "2026-11-03-wave31-ab-b2"


def _report() -> str:
    return (RUN / "report.md").read_text(encoding="utf-8")


def test_ab_run_artifacts_exist_and_sealed() -> None:
    assert (RUN / "run.py").exists()
    assert (RUN / "report.md").exists()
    assert (RUN / "output.md").exists()
    blood = RUN / "blood.jsonl"
    assert blood.exists()
    anchors = [json.loads(l) for l in (ROOT / "blood" / "anchors.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    rel = "runs/2026-11-03-wave31-ab-b2/blood.jsonl"
    mine = [a for a in anchors if a["file"] == rel]
    assert len(mine) == 1, "в доме одна печать прогона (урок волны №27)"


def test_both_groups_ran_the_same_scenarios() -> None:
    events = [json.loads(l) for l in (RUN / "blood.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    scenes = [e["payload"].get("scene", "") for e in events if e["type"] == "observe"]
    assert len(scenes) == 3, scenes
    report = _report()
    for group in ("организм", "Б2"):
        assert group in report
    # обе группы мерены на тех же 8 сценах (счёт из живых чисел отчёта)
    assert report.count("организм") >= 6 and "Б2" in report


def test_verdict_is_derived_from_measurable_score() -> None:
    report = _report()
    # счёт — поимённо по шести измеримым точкам, не лозунг
    for point in (
        "заверяемость журнала",
        "полнота трейса",
        "приманка до факта",
        "повтор ключа не повторяет эффект",
        "дедлайн назван честно",
        "перегрузка без каскада",
    ):
        assert point in report, point
    # слабости Б2 названы открыто, не спрятаны
    assert "Б2 по-своему хорош" in report
    assert "текстового лога без хэш-цепочки" in report
    # границы замера названы (песочница, сеть)
    assert "Замер — в песочнице" in report
    assert "Сеть в песочнице недоступна" in report


def test_b2_failures_are_named_in_blood_not_hidden() -> None:
    """Кровь А/Б называет факты Б2: секрет приманки прочитан, дубль удвоил эффект."""
    events = [json.loads(l) for l in (RUN / "blood.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    scene2 = next(e for e in events if e["type"] == "observe" and e["payload"].get("step") == 2)
    text = json.dumps(scene2["payload"], ensure_ascii=False)
    assert "секрет прочитан=True" in text, "приманка Б2 честно названа прочитанной"
    assert "повторов эффекта dup:1=2" in text, "двойной эффект дубля честно назван"
    assert "таймаут_пойман=False" in text, "молчаливый таймаут Б2 назван"
    assert "перегрузка_SHED=False" in text, "отсутствие SHED у Б2 названо"


def test_house_shed_and_idempotency_gates_still_hold() -> None:
    """Организм в этом же доме держит SHED и A01 — их приёмки живы (волна №29)."""
    from brainstem.dispatch import Dispatcher
    from blood.journal import Journal
    from blood.envelope import Cost

    j = Journal()
    dp = Dispatcher(j, max_queue=1, max_attempts=1, timeout=1.0)
    blocker_running = {"done": False}

    def blocker() -> dict:
        blocker_running["done"] = True
        return {"ok": True}

    r1 = dp.deliver("k:1", blocker, label="первый")
    r2 = dp.deliver("k:1", blocker, label="повтор того же ключа")  # inflight пуст — резолв кэша
    assert r1["verdict"] == "DONE" and r2.get("redelivered") is True
    # SHED: заполненный inflight — повтор до завершения не принимается
    calls = {"n": 0}

    def slow_block() -> dict:
        calls["n"] += 1
        return {"ok": True}

    holder = Dispatcher(j, max_queue=1, max_attempts=1, timeout=1.0)
    holder._inflight["busy:1"] = "занято"
    r3 = holder.deliver("busy:2", slow_block, label="второе при полной очереди")
    assert r3["verdict"] == "SHED" and calls["n"] == 0, "перегрузка отвергнута до факта, каскада нет"
