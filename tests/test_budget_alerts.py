# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмки бюджета метаболизма и алертов — SPEC-0001 G3 (M3).

Три границы бюджета (SPEC-0001 G3, M3):
- трейс-бюджет: исчерпание (граница включена) → `halt`; порог alert_ratio от
  лимита → ровно один `alert` на трейс (organ "self", source brainstem);
- per-call лимит органа (organ_budgets): цена вызова СТРОГО больше лимита →
  `alert` с именем органа (вызов уже оплачен кровью — это не запрет, а алерт);
  ровно на границе — тишина.

Проверки трейс-бюджета выполняются ПЕРЕД каждым шагом по totals крови,
поэтому событие появляется на первой проверке, где totals перевалил порог.
Цена вызова управляется размером пейлоада: FakeEcho берёт
tokens_in = len(str(payload)), tokens_out = 1, seconds = 0.01 (tests/fakes.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from blood.journal import Journal
from brainstem import Budget, Loop
from synapse.gateway import Gateway

from .conftest import MANIFEST, step  # noqa: TID252


def echo_payload(tokens_in: int) -> dict[str, str]:
    """Пейлоад под заданную цену вызова: FakeEcho берёт tokens_in = len(str(payload))."""
    payload: dict[str, str] = {"data": ""}
    payload["data"] = "x" * (tokens_in - len(str(payload)))
    assert len(str(payload)) == tokens_in  # страховка от смены формата repr
    return payload


def _manifest_with_metabolism(tmp_path: Path) -> Path:
    """Манифест общего вида + орган metabolism на FakeEcho — для per-call приёмок."""
    organs = [dict(organ) for organ in MANIFEST["organs"]]
    organs.append(
        {
            "name": "metabolism",
            "system": "metabolism",
            "mode": "dependency",
            "upstream": "https://example.invalid/metabolism",
            "license": "MIT",
            "transport": "stdio",
            "command": "fake-metabolism",
            "healthcheck": "initialize handshake",
            "tools": ["echo"],
            "authority": {"fs": "read-only", "network": "none"},
            "adapter": "tests.fakes:FakeEcho",
        }
    )
    path = tmp_path / "mcp-manifest.yaml"
    path.write_text(yaml.safe_dump({**MANIFEST, "organs": organs}, allow_unicode=True), encoding="utf-8")
    return path


def _metabolism_loop(tmp_path: Path, organ_budgets: dict[str, Budget]) -> tuple[Loop, Journal]:
    """Цикл с per-call лимитами и органом metabolism; кровь — свежий Journal."""
    journal = Journal()
    gateway = Gateway(_manifest_with_metabolism(tmp_path), journal)
    return Loop(gateway, journal, organ_budgets=organ_budgets), journal


# --- трейс-бюджет: alert по alert_ratio, не более одного на трейс ---


def test_alert_once_at_threshold(loop, journal) -> None:
    """totals перевалил alert_ratio*лимит → ровно ОДИН alert; повторное пересечение молчит."""
    budget = Budget(tokens_in=100, alert_ratio=0.5)  # порог алерта = 50
    plan = [step(payload=echo_payload(30)) for _ in range(4)]
    assert loop.run(plan, trace_id="alert-once", budget=budget) is True

    # Проверки перед шагами видят totals: 0, 30, 60 (>= 50 → alert), 90 (уже алертили — тишина).
    alerts = journal.by_type("alert")
    assert len(alerts) == 1
    (alert,) = alerts
    assert alert["source"] == "brainstem"
    assert alert["organ"] == "self"
    assert "бюджет близок" in alert["payload"]["reason"]
    assert alert["payload"]["at_step"] == 2  # сработал на totals=60, перед 3-м шагом
    assert journal.totals("alert-once").tokens_in == 120  # 4 вызова по 30
    # Исчерпания (100) ни одна проверка не видела → halt нет; второй alert не пишется.
    assert journal.by_type("halt") == ()


def test_halt_on_exhaustion_unchanged(loop, journal) -> None:
    """Исчерпание (граница включена) → halt как раньше; alert при 30 < 0.8*40=32 не пишется ни разу."""
    budget = Budget(tokens_in=40)  # alert_ratio по умолчанию 0.8 → порог алерта 32
    plan = [step(payload=echo_payload(30)) for _ in range(3)]
    assert loop.run(plan, trace_id="halt-1", budget=budget) is False

    # Перед 1-м и 2-м шагами totals 0 и 30 < 40 → продолжаем;
    # перед 3-м totals=60 >= 40 → halt, третий шаг не планируется.
    assert len(journal.by_type("plan")) == 2
    (halt,) = journal.by_type("halt")
    assert halt["source"] == "brainstem"
    assert halt["organ"] == "self"
    assert "бюджет исчерпан" in halt["payload"]["reason"]
    # 30 >= 32? нет — до halt ни одна проверка порога не проходит → alert'ов нет вообще.
    assert journal.by_type("alert") == ()


def test_no_alert_below_ratio(loop, journal) -> None:
    """totals=60 << порога 800 — ни одного alert, план выполняется целиком."""
    budget = Budget(tokens_in=1000)  # порог алерта 0.8*1000 = 800
    plan = [step(payload=echo_payload(30)) for _ in range(2)]
    assert loop.run(plan, trace_id="quiet", budget=budget) is True
    assert journal.by_type("alert") == ()
    assert journal.by_type("halt") == ()
    assert journal.totals("quiet").tokens_in == 60


# --- per-call лимиты органов: превышение (строго больше) — алерт, не запрет ---


def test_per_call_exceeded_alert(tmp_path) -> None:
    """Цена вызова 30 > лимита 10 → alert органа metabolism; сам вызов состоялся."""
    loop, journal = _metabolism_loop(tmp_path, {"metabolism": Budget(tokens_in=10)})
    assert loop.run([step(organ="metabolism", payload=echo_payload(30))], trace_id="percall-over") is True

    (alert,) = journal.by_type("alert")
    assert alert["organ"] == "metabolism"
    assert alert["source"] == "brainstem"
    assert "лимит вызова" in alert["payload"]["reason"]
    assert alert["payload"]["tool"] == "echo"
    # Per-call — алерт, а не запрет: act и observe на месте, reflect удовлетворён.
    assert [e["type"] for e in journal.by_trace("percall-over")] == ["plan", "act", "alert", "observe", "reflect"]
    (reflect,) = journal.by_type("reflect")
    assert reflect["payload"]["satisfied"] is True


def test_per_call_within_limit_silent(tmp_path) -> None:
    """Цена вызова 30 <= лимита 100 — тишина, обычный цикл без алертов."""
    loop, journal = _metabolism_loop(tmp_path, {"metabolism": Budget(tokens_in=100)})
    assert loop.run([step(organ="metabolism", payload=echo_payload(30))], trace_id="percall-ok") is True
    assert journal.by_type("alert") == ()
    assert [e["type"] for e in journal.by_trace("percall-ok")] == ["plan", "act", "observe", "reflect"]


def test_per_call_unknown_organ_silent(tmp_path) -> None:
    """Лимит задан для другого органа — вызов metabolism молчит (лимит не задан → тишина)."""
    loop, journal = _metabolism_loop(tmp_path, {"reserve-c": Budget(tokens_in=1)})
    assert loop.run([step(organ="metabolism", payload=echo_payload(30))], trace_id="percall-other") is True
    assert journal.by_type("alert") == ()
    assert [e["type"] for e in journal.by_trace("percall-other")] == ["plan", "act", "observe", "reflect"]


def test_per_call_seconds_budget(tmp_path) -> None:
    """Per-call лимит в секундах: 0.01 > 0.001 → alert именно по seconds."""
    loop, journal = _metabolism_loop(tmp_path, {"metabolism": Budget(seconds=0.001)})
    assert loop.run([step(organ="metabolism", payload=echo_payload(30))], trace_id="percall-sec") is True

    (alert,) = journal.by_type("alert")
    assert alert["organ"] == "metabolism"
    assert "лимит вызова" in alert["payload"]["reason"]
    assert "seconds" in alert["payload"]["reason"]


def test_per_call_not_flagged_at_boundary(tmp_path) -> None:
    """Граница per-call НЕ включена: ровно 30 при лимите 30 — не «строго больше», тишина."""
    loop, journal = _metabolism_loop(tmp_path, {"metabolism": Budget(tokens_in=30)})
    assert loop.run([step(organ="metabolism", payload=echo_payload(30))], trace_id="percall-edge") is True
    assert journal.by_type("alert") == ()
    assert [e["type"] for e in journal.by_trace("percall-edge")] == ["plan", "act", "observe", "reflect"]


# --- совместимость и порядок записей ---


def test_backward_compatible(loop, journal) -> None:
    """Loop(gateway, journal) без organ_budgets и budget=None — поведение прежнее."""
    assert loop.run([step()], trace_id="legacy") is True
    assert [e["type"] for e in journal.by_trace("legacy")] == ["plan", "act", "observe", "reflect"]
    assert journal.by_type("alert") == ()
    assert journal.by_type("halt") == ()


def test_alert_and_halt_ordering(loop, journal) -> None:
    """Alert на пороге (30 >= 30) пишется раньше halt на границе (60 >= 60); по одному каждому."""
    budget = Budget(tokens_in=60, alert_ratio=0.5)  # порог алерта = 30
    plan = [step(payload=echo_payload(30)) for _ in range(3)]
    assert loop.run(plan, trace_id="order", budget=budget) is False

    events = journal.by_trace("order")
    alerts = [e for e in events if e["type"] == "alert"]
    halts = [e for e in events if e["type"] == "halt"]
    assert len(alerts) == 1
    assert len(halts) == 1
    assert events.index(alerts[0]) < events.index(halts[0])  # alert раньше halt в крови
    assert "бюджет близок" in alerts[0]["payload"]["reason"]
    assert "бюджет исчерпан" in halts[0]["payload"]["reason"]
    assert alerts[0]["payload"]["at_step"] == 1  # totals=30 >= 30, перед 2-м шагом
    assert halts[0]["payload"]["at_step"] == 2  # totals=60 >= 60, перед 3-м шагом
