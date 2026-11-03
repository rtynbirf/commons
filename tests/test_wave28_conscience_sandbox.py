# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмки волны №28 — Ф-2 органы-функции (docs/TZ.md ТЗ-2.1, ТЗ-2.2).

ТЗ-2.1 (A19) — совесть: `blood/conscience.py` calibrate() сверяет заявление
тела о провалах с фактом крови (счётчик W-0021) — на ложной посылке не
поддакивает: расхождение названо поимённо; грамматика посылки fail-closed.

ТЗ-2.2 (A20) — творческая песочница: `brainstem/sandbox.py` — гипотезы
(творчество тела) живут в крови с trust unverified и маркером «гипотеза, не
факт»; шаг плана на гипотезе (Step.basis) без критерия проверки — veto до
факта: гипотеза не становится фактом; ссылка на гипотезу, которой нет в
крови, — тоже veto (незаявленное не достраивается).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from blood.envelope import Cost, make
from blood.journal import Journal
from brainstem.loop import Loop, Step
from brainstem.sandbox import SANDBOX_NOTE, Sandbox
from blood.conscience import calibrate
from synapse.gateway import Gateway
from tests.fakes import FakeEcho  # здоровый орган-эхо (результат {"echo":…, "tool":…})

TRACE = "wave28-conscience-sandbox"


def _journal_with_failures() -> Journal:
    journal = Journal()
    journal.append(make(
        "reflect", "brainstem", "self", "tr-a", {"verdict": "работа"}, Cost(0, 0, 0.1),
    ))
    journal.append(make("error", "brainstem", "self", "tr-a", {"reason": "канал упал"}, Cost(0, 0, 0.0)))
    journal.append(make("error", "brainstem", "self", "tr-b", {"reason": "таймаут"}, Cost(0, 0, 0.0)))
    journal.append(make("halt", "brainstem", "self", "tr-b", {"reason": "бюджет"}, Cost(0, 0, 0.0)))
    return journal


# --- ТЗ-2.1: совесть (A19) ----------------------------------------------------


def test_conscience_disagrees_with_false_premise() -> None:
    """A19: на ложной посылке совесть не поддакивает — расхождение поимённо."""
    journal = _journal_with_failures()
    report = calibrate({"refusals": 0}, journal)
    assert report["agree"] is False
    assert report["disagreements"], "ложная посылка обязана быть названной"
    assert report["facts"]["total"] == 3
    words = report["words"]
    assert "Не согласен" in words and "3" in words


def test_conscience_agrees_with_true_premise_and_names_evidence() -> None:
    """Верная посылка — согласие с доказательством, а не просто «да»."""
    journal = _journal_with_failures()
    report = calibrate({"refusals": 3, "refusal_types": ["error", "halt"]}, journal)
    assert report["agree"] is True
    assert report["disagreements"] == []
    assert report["facts"]["by_type"] == {"error": 2, "halt": 1}
    assert "Согласен" in report["words"]


def test_conscience_names_traces_of_failures() -> None:
    """Посылка о провальных трейсах сверяется поимённо: чужой/пропущенный назван."""
    journal = _journal_with_failures()
    report = calibrate({"traces_failed": ["tr-a"]}, journal)
    assert report["agree"] is False
    joined = json.dumps(report, ensure_ascii=False)
    assert "tr-b" in joined, "реально проваленный трейс назван"
    report2 = calibrate({"traces_failed": ["tr-a", "tr-b"]}, journal)
    assert report2["agree"] is True


def test_conscience_premise_grammar_is_fail_closed() -> None:
    """Незаявленное в посылке не достраивается: чужой ключ — ValueError."""
    journal = _journal_with_failures()
    with pytest.raises(ValueError):
        calibrate({"настроение": "хорошее"}, journal)


def test_conscience_empty_blood_agrees_with_zero_premise() -> None:
    """Пустая кровь: посылка «отказов не было» — согласие, доказательство названо."""
    journal = Journal()
    report = calibrate({"refusals": 0}, journal)
    assert report["agree"] is True
    assert report["facts"]["total"] == 0


def test_conscience_accepts_spilled_blood_path(tmp_path: Path) -> None:
    """Совесть читает и пролитую кровь (путь к файлу), не только живую память."""
    path = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.attach(path)
    journal.append(make("error", "brainstem", "self", "tr-x", {"reason": "упало"}, Cost(0, 0, 0.0)))
    journal.close()
    report = calibrate({"refusals": 1}, path)
    assert report["agree"] is True
    report2 = calibrate({"refusals": 0}, path)
    assert report2["agree"] is False


# --- ТЗ-2.2: творческая песочница (A20) ---------------------------------------


class _SpyOrgan:
    def __init__(self, entry: dict) -> None:
        self.entry = entry
        self.called = False

    def health(self) -> bool:
        return True

    def invoke(self, tool: str, payload: dict) -> tuple[dict, Cost]:
        self.called = True
        return {"done": True}, Cost(1, 1, 0.01)


@pytest.fixture()
def spy_gateway(tmp_path: Path):
    manifest = {
        "version": "0.1.0",
        "updated": "2026-11-03",
        "transport_default": "stdio",
        "organs": [{
            "name": "creator",
            "system": "cognition",
            "mode": "dependency",
            "upstream": "https://example.invalid/creator",
            "license": "MIT",
            "transport": "stdio",
            "command": "fake-creator",
            "healthcheck": "initialize handshake",
            "tools": ["write"],
            "authority": {"fs": {"mode": "read-only", "paths": [str(tmp_path)]}, "network": "none", "process": "none"},
            "adapter": "tests.fakes:FakeEcho",
        }],
    }
    import yaml

    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    journal = Journal()
    gw = Gateway(manifest_path, journal=journal)
    return gw, journal


def test_hypothesis_is_unverified_and_not_a_fact(spy_gateway) -> None:
    """A20: гипотеза живёт в крови с trust unverified и маркером «гипотеза, не факт»."""
    gw, journal = spy_gateway
    sandbox = Sandbox(journal)
    hyp = sandbox.propose("если писать в файл байтами, потеря меньше")
    assert hyp["type"] == "reflect"
    assert hyp["trust"] == "unverified"
    assert hyp["payload"]["sandbox"] is True
    assert hyp["payload"]["hypothesis"] == "если писать в файл байтами, потеря меньше"
    assert SANDBOX_NOTE in json.dumps(hyp, ensure_ascii=False)
    assert sandbox.hypotheses()[0]["id"] == hyp["id"]


def test_step_on_hypothesis_without_criterion_is_vetoed(spy_gateway) -> None:
    """Гипотеза не становится фактом: шаг на гипотезе без Step.accept — veto до факта."""
    gw, journal = spy_gateway
    sandbox = Sandbox(journal)
    hyp = sandbox.propose("гипотеза про запись")
    loop = Loop(gw, journal)
    plan = [Step(organ="creator", tool="write", intent="запись по гипотезе",
                 payload={"on_hypothesis": True}, basis=hyp["id"])]
    assert loop.run(plan, trace_id=TRACE) is False
    vetoes = [e for e in journal.all() if e["type"] == "veto"]
    assert vetoes and "гипотеза" in vetoes[-1]["payload"]["reason"]
    acts = [e for e in journal.all() if e["type"] == "act"]
    assert acts == [], "акта нет: гипотеза не стала фактом"


def test_step_on_unknown_hypothesis_is_vetoed(spy_gateway) -> None:
    """Ссылка на гипотезу, которой нет в крови, — veto (незаявленное не достраивается)."""
    gw, journal = spy_gateway
    loop = Loop(gw, journal)
    plan = [Step(organ="creator", tool="write", intent="запись",
                 payload={}, basis="00000000-0000-4000-8000-000000000000",
                 accept={"type": "object"})]
    assert loop.run(plan, trace_id=TRACE) is False
    vetoes = [e for e in journal.all() if e["type"] == "veto"]
    assert vetoes and "нет в крови" in vetoes[-1]["payload"]["reason"]
    assert [e for e in journal.all() if e["type"] == "act"] == []


def test_step_on_hypothesis_with_criterion_executes_and_names_basis(spy_gateway) -> None:
    """Проверенный путь: гипотеза + критерий приёмки (W-0027) — шаг исполняется,
    план несёт basis ДО факта, reflect называет критерий."""
    gw, journal = spy_gateway
    sandbox = Sandbox(journal)
    hyp = sandbox.propose("гипотеза про запись")
    loop = Loop(gw, journal)
    plan = [Step(organ="creator", tool="write", intent="запись по гипотезе",
                 payload={"on_hypothesis": True}, basis=hyp["id"],
                 accept={"type": "object"},
                 reversibility="reversible")]
    assert loop.run(plan, trace_id=TRACE) is True
    plans = [e for e in journal.all() if e["type"] == "plan"]
    assert plans and plans[0]["payload"]["basis"] == hyp["id"]
    assert [e for e in journal.all() if e["type"] == "act"], "проверенная гипотеза может стать шагом"
    reflects = [e for e in journal.all() if e["type"] == "reflect" and "criterion" in (e.get("payload") or {})]
    assert reflects, "рефлексия назвала критерий"


def test_old_plans_without_basis_stay_valid(spy_gateway) -> None:
    """Аддитивность: шаги без basis живут как раньше (старые планы валидны)."""
    gw, journal = spy_gateway
    loop = Loop(gw, journal)
    plan = [Step(organ="creator", tool="write", intent="обычный шаг",
                 payload={}, accept={"type": "object"})]
    assert loop.run(plan, trace_id=TRACE) is True
    assert [e for e in journal.all() if e["type"] == "act"]
