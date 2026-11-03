# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмки волны №24 — внешний аварийный стоп петли (W-0033) и гейт «поведение без спеки» (W-0030).

W-0033 (дыра ревизии 2026-11-03 «аварийный останов петли», SPEC-0001 v0.6.0 п.8):
внутри одного прогона остановить петлю может только её собственный REFLECT —
а рефлексия M1 тахометр (F-06). Стоп-кран обязан жить снаружи: сигнал,
проверяемый на границе шагов, — halt-конверт с source=external, до факта.
Уже вызванный орган не прерывается (честная граница: он доезжает и оплачивается
кровью), следующий шаг не начинается. Упавший сигнал — тоже стоп (fail-closed).

W-0030 (зерно D3 арбитража коллег 2026-11-03, находка F-09, гейт доктора):
изменение публичного поведения дома (blood/, synapse/, brainstem/) без правки
specs/ — блоха. Принцип «спека меняется раньше кода» становится машиной,
а не призывом. Git недоступен — fail-closed, красный без суждения.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Callable

import pytest

from blood.journal import Journal
from brainstem import Budget, Loop, Step
from brainstem.stop import file_stop_signal
from synapse.gateway import Gateway

from .conftest import MANIFEST, step  # noqa: TID252

REPO_ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("doctor", REPO_ROOT / "scripts" / "doctor.py")
doctor = importlib.util.module_from_spec(_spec)
sys.modules["doctor"] = doctor
_spec.loader.exec_module(doctor)


# --- оснастка ---


@pytest.fixture()
def manifest_path(tmp_path: Path) -> Path:
    import yaml

    path = tmp_path / "mcp-manifest.yaml"
    path.write_text(yaml.safe_dump(MANIFEST, allow_unicode=True), encoding="utf-8")
    return path


@pytest.fixture()
def gateway(manifest_path: Path) -> Gateway:
    return Gateway(manifest_path, Journal())


def _halts(events: list[dict]) -> list[dict]:
    return [e for e in events if e["type"] == "halt"]


def _acts(events: list[dict]) -> list[dict]:
    return [e for e in events if e["type"] == "act"]


# --- W-0033: внешний аварийный стоп ---


def test_external_stop_between_steps(gateway: Gateway) -> None:
    """Сигнал на границе шагов: шаг 0 исполнен и оплачен, шаг 1 не начался, halt с source=external."""
    fired = {"after_first": False}

    def signal() -> str | None:
        return "Человек нажал стоп-кран" if fired["after_first"] else None

    def spy_signal() -> str | None:
        # сигнал опрашивается на границе; после первого исполненного шага — стоп
        if len([e for e in gateway.journal.all() if e["type"] == "reflect"]) >= 1:
            fired["after_first"] = True
        return signal()

    loop = Loop(gateway, gateway.journal, stop_signal=spy_signal)
    plan = [step(payload={"n": 1}), step(payload={"n": 2}), step(payload={"n": 3})]
    assert loop.run(plan) is False
    events = gateway.journal.all()
    assert len(_acts(events)) == 1, "шаг 0 доезжает, шаг 1 не начинается"
    halts = _halts(events)
    assert len(halts) == 1
    assert halts[0]["payload"]["source"] == "external"
    assert "стоп" in halts[0]["payload"]["reason"]
    assert halts[0]["payload"]["at_step"] == 1


def test_external_stop_before_first_step(gateway: Gateway) -> None:
    """Стоп-кран нажат до запуска: ни одного акта, halt на шаге 0."""
    loop = Loop(gateway, gateway.journal, stop_signal=lambda: "авария до старта")
    assert loop.run([step(), step()]) is False
    events = gateway.journal.all()
    assert _acts(events) == []
    halts = _halts(events)
    assert len(halts) == 1
    assert halts[0]["payload"]["at_step"] == 0
    assert halts[0]["payload"]["source"] == "external"


def test_signal_returning_none_means_continue(gateway: Gateway) -> None:
    """Сигнал молчит на всех границах — трейс проходит целиком, halt нет."""
    loop = Loop(gateway, gateway.journal, stop_signal=lambda: None)
    assert loop.run([step(), step()]) is True
    events = gateway.journal.all()
    assert len(_acts(events)) == 2
    assert _halts(events) == []


def test_no_signal_at_all_means_old_semantics(gateway: Gateway) -> None:
    """Сигнал не подключён — прежние семантики цикла (аддитивно)."""
    loop = Loop(gateway, gateway.journal)
    assert loop.run([step()]) is True
    assert _halts(gateway.journal.all()) == []


def test_broken_signal_fails_closed(gateway: Gateway) -> None:
    """Сигнал упал — это тоже стоп: авария в нерве не молчит и не разрешает продолжение."""

    def signal() -> str | None:
        raise RuntimeError("нерв оборван")

    loop = Loop(gateway, gateway.journal, stop_signal=signal)
    assert loop.run([step()]) is False
    events = gateway.journal.all()
    assert _acts(events) == []
    halts = _halts(events)
    assert len(halts) == 1
    assert "стоп-сигнал упал" in halts[0]["payload"]["reason"]
    assert "нерв оборван" in halts[0]["payload"]["reason"]


def test_external_stop_wins_over_budget(gateway: Gateway) -> None:
    """Стоп-кран главнее бюджета: оба условия на границе — в крови halt от стопа."""
    loop = Loop(gateway, gateway.journal, stop_signal=lambda: "стоп важнее денег")
    budget = Budget(tokens_in=1)  # фейковый вызов и так съест больше
    assert loop.run([step(payload={"data": "x" * 50})], budget=budget) is False
    halts = _halts(gateway.journal.all())
    assert len(halts) == 1
    assert halts[0]["payload"]["source"] == "external"


def test_steps_before_stop_remain_in_blood(gateway: Gateway) -> None:
    """Уже сделанное не вычёркивается: act/observe/reflect шага 0 остаются в крови."""
    reflect_seen = {"n": 0}

    def signal() -> str | None:
        return "стоп" if reflect_seen["n"] else None

    def spy_signal() -> str | None:
        reflect_seen["n"] = len([e for e in gateway.journal.all() if e["type"] == "reflect"])
        return signal()

    loop = Loop(gateway, gateway.journal, stop_signal=spy_signal)
    loop.run([step(payload={"n": 1}), step(payload={"n": 2})])
    types = [e["type"] for e in gateway.journal.all()]
    assert "act" in types and "observe" in types and "reflect" in types
    assert types[-1] == "halt"


def test_external_stop_halt_is_reconstructible(gateway: Gateway, tmp_path: Path) -> None:
    """G1: отказной выход по стоп-крану завершён halt — трейс полон, resume честен."""
    from blood.resume import reconstruct

    def spy_signal() -> str | None:
        return "стоп" if any(e["type"] == "reflect" for e in gateway.journal.all()) else None

    loop = Loop(gateway, gateway.journal, stop_signal=spy_signal)
    trace_id = "t-stop-1"
    assert loop.run([step(), step()], trace_id=trace_id) is False
    gateway.journal.to_jsonl(tmp_path / "blood.jsonl")
    session = reconstruct(tmp_path / "blood.jsonl", trace_id)
    assert session["complete"] is True, "трейс закрыт по-записанному"
    assert len(session["halts"]) == 1, "отказной выход завершён halt (G1)"
    assert "внешний аварийный стоп" in session["halts"][0]["reason"]


# --- W-0033: файловый нерв (живой хост) ---


def test_file_signal_silent_without_file(tmp_path: Path) -> None:
    assert file_stop_signal(tmp_path / "stop")() is None


def test_file_signal_reads_reason_and_consumes_file(tmp_path: Path) -> None:
    stop = tmp_path / "stop"
    stop.write_text("Человек остановил организм\n", encoding="utf-8")
    signal = file_stop_signal(stop)
    assert signal() == "Человек остановил организм"
    assert not stop.exists(), "сигнал потреблён: остановка живёт в крови, не в файле"
    assert signal() is None, "повторный опрос — стопа нет"


def test_file_signal_empty_file_named_honestly(tmp_path: Path) -> None:
    stop = tmp_path / "stop"
    stop.write_text("\n", encoding="utf-8")
    assert file_stop_signal(stop)() == "стоп-файл"


def test_file_signal_survives_unlink_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Удалить не удалось — сигнал всё равно назван (безопасное направление)."""
    stop = tmp_path / "stop"
    stop.write_text("стоп\n", encoding="utf-8")

    def broken_unlink(self: Path) -> None:
        raise OSError("диск только для чтения")

    monkeypatch.setattr(Path, "unlink", broken_unlink)
    assert file_stop_signal(stop)() == "стоп"


# --- W-0030: гейт «поведение без спеки» ---


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _fake_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    (tmp_path / "README.md").write_text("дом\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def test_spec_drift_gate_names_the_path(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    (root / "synapse").mkdir(parents=True)
    (root / "synapse" / "gateway.py").write_text("x = 1\n", encoding="utf-8")
    ok, fleas = doctor.check_spec_drift(root)
    assert ok == 0
    assert len(fleas) == 1
    assert "synapse/gateway.py" in fleas[0]
    assert "спека" in fleas[0]


def test_spec_drift_green_with_specs_change(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    (root / "blood").mkdir(parents=True)
    (root / "specs").mkdir(parents=True)
    (root / "blood" / "envelope.py").write_text("x = 1\n", encoding="utf-8")
    (root / "specs" / "SPEC-0003-blood-envelope.md").write_text("спека\n", encoding="utf-8")
    assert doctor.check_spec_drift(root) == (1, [])


def test_spec_drift_green_without_behavior_change(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    (root / "README.md").write_text("только книжки\n", encoding="utf-8")
    assert doctor.check_spec_drift(root) == (1, [])


def test_spec_drift_sees_untracked_new_behavior(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    new_dir = root / "brainstem"
    new_dir.mkdir()
    (new_dir / "renegade.py").write_text("x = 1\n", encoding="utf-8")
    ok, fleas = doctor.check_spec_drift(root)
    assert ok == 0
    assert any("brainstem/renegade.py" in f for f in fleas)


def test_spec_drift_fail_closed_without_git(tmp_path: Path) -> None:
    (tmp_path / "blood").mkdir()
    ok, fleas = doctor.check_spec_drift(tmp_path)
    assert ok == 0
    assert fleas, "без git гейт обязан быть красным, а не слепым"


def test_spec_drift_honours_base_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fake_repo(tmp_path)
    base = _git(root, "rev-parse", "HEAD").strip()
    (root / "blood").mkdir(parents=True)
    (root / "blood" / "envelope.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "behavior without spec")
    # база = текущий HEAD: дифф пуст, гейт зелен
    monkeypatch.setenv("SPEC_DRIFT_BASE", "HEAD")
    assert doctor.check_spec_drift(root) == (1, [])
    # база = коммит до правки: поведение видно, спеки нет — красный
    monkeypatch.setenv("SPEC_DRIFT_BASE", base)
    ok, fleas = doctor.check_spec_drift(root)
    assert ok == 0
    assert any("blood/envelope.py" in f for f in fleas)


def test_spec_drift_stands_in_doctor_gates() -> None:
    assert any(name == "spec-drift" for name, _ in doctor.GATES)
