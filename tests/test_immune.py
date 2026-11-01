# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмка SPEC-0006: иммунный барьер — пара (license, mode) -> вердикт.

Матрица — данные (G2): правка license-matrix.yaml меняет вердикт без правки кода.
Fail-closed (G1): неизвестная лицензия запрещена во встраивание, ограниченная —
в core_modes. Гейт run_check/CLI возвращает 0 только если все органы прошли.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
import yaml

from immune import Decision, check_entries, load_matrix, run_check, verdict
from immune.barrier import main

MATRIX = load_matrix()
REGISTRY_PATH = Path(__file__).resolve().parents[1] / "organs" / "registry.yaml"


# --- allowed: проход во всех режимах ---


@pytest.mark.parametrize("license_name", MATRIX["allowed"])
@pytest.mark.parametrize("mode", MATRIX["modes"])
def test_allowed_license_passes_in_every_mode(license_name: str, mode: str) -> None:
    """Разрешённая повсеместно лицензия проходит барьер в любом из шести режимов."""
    d = verdict(license_name, mode, MATRIX)
    assert d.ok, d.reason
    assert d.rule == "allowed"


# --- restricted: запрет во встраивании, допуск вне тела ---


@pytest.mark.parametrize("license_name", MATRIX["restricted"])
def test_restricted_license_core_denied_outside_allowed(license_name: str) -> None:
    """Ограниченная лицензия: deny в core_modes (встраивание), allow вне тела."""
    outside = [m for m in MATRIX["modes"] if m not in MATRIX["core_modes"]]
    for core in MATRIX["core_modes"]:
        d = verdict(license_name, core, MATRIX)
        assert not d.ok, (license_name, core, d.reason)
        assert d.rule == "restricted"
    for mode in outside:
        d = verdict(license_name, mode, MATRIX)
        assert d.ok, (license_name, mode, d.reason)
        assert d.rule == "restricted"


# --- conditional: dify допустима только вне встраивания ---


def test_conditional_license_dify_adapter_ok_dependency_denied() -> None:
    """Условная лицензия dify: adapter — проход, dependency (встраивание) — отказ."""
    ok = verdict("Apache-2.0 с условиями", "adapter", MATRIX)
    assert ok.ok and ok.rule == "conditional"
    deny = verdict("Apache-2.0 с условиями", "dependency", MATRIX)
    assert not deny.ok and deny.rule == "conditional"


# --- G1: fail-closed на неизвестной лицензии ---


def test_unknown_license_fail_closed_in_core_unrecognized_outside() -> None:
    """G1 fail-closed: неизвестная лицензия в dependency запрещена; в reference — unrecognized."""
    core = verdict("My-Custom-License", "dependency", MATRIX)
    assert not core.ok and core.rule == "fail-closed"
    outer = verdict("My-Custom-License", "reference", MATRIX)
    assert outer.ok and outer.rule == "unrecognized"


# --- неизвестный режим ---


def test_unknown_mode_rejected() -> None:
    """Режим вне матрицы — отказ независимо от лицензии (rule='unknown-mode')."""
    d = verdict("MIT", "embedded", MATRIX)
    assert not d.ok and d.rule == "unknown-mode"


# --- отсутствие данных ---


def test_missing_license_or_mode_rejected() -> None:
    """Пустая/отсутствующая лицензия или режим — отказ (rule='missing'), в том числе в записях."""
    for license_name, mode in (("", "dependency"), ("MIT", ""), (None, None)):
        d = verdict(license_name, mode, MATRIX)  # type: ignore[arg-type]
        assert not d.ok and d.rule == "missing"

    decisions = check_entries(
        [
            {"name": "no-license", "mode": "dependency"},
            {"name": "no-mode", "license": "MIT"},
            {"license": "MIT", "mode": "dependency"},  # нет имени
            {"repo": "ok/repo", "license_pre": "MIT", "mode": "reference"},  # поля реестра
        ],
        MATRIX,
    )
    assert [d.rule for d in decisions] == ["missing", "missing", "missing", "allowed"]


# --- G2: матрица — данные, вердикт меняется правкой файла ---


def test_matrix_as_data_changes_verdict_without_code_change(tmp_path: Path) -> None:
    """G2: allowed пуст, GPL-3.0 перенесён в allowed — вердикт меняется, код нет."""
    deny = verdict("GPL-3.0", "dependency", MATRIX)
    assert not deny.ok and deny.rule == "restricted"

    custom = {
        "version": "0.0.0-test",
        "modes": MATRIX["modes"],
        "core_modes": MATRIX["core_modes"],
        "allowed": ["GPL-3.0"],
    }
    path = tmp_path / "custom-matrix.yaml"
    path.write_text(yaml.safe_dump(custom, allow_unicode=True), encoding="utf-8")
    custom_matrix = load_matrix(path)

    allow = verdict("GPL-3.0", "dependency", custom_matrix)
    assert allow.ok and allow.rule == "allowed"
    flipped = verdict("MIT", "dependency", custom_matrix)
    assert not flipped.ok and flipped.rule == "fail-closed"


def test_load_matrix_corrupted_raises(tmp_path: Path) -> None:
    """Матрица без modes/core_modes повреждена -> ValueError (fail-closed на уровне данных)."""
    path = tmp_path / "broken-matrix.yaml"
    path.write_text("allowed: [MIT]\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_matrix(path)


# --- матрица покрывает весь реестр ---


def test_matrix_covers_every_registry_license() -> None:
    """Каждая пара (license_pre, mode) реестра явна в матрице: ни unrecognized, ни fail-closed."""
    registry = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    for entry in registry["organs"]:
        for mode in registry["modes"]:
            d = verdict(entry["license_pre"], mode, MATRIX)
            assert d.rule not in ("unrecognized", "fail-closed"), (entry["repo"], mode, d.rule)
    # и собственные пары реестра барьер проходят целиком (гейт python -m immune зелёный)
    assert all(d.ok for d in check_entries(registry["organs"], MATRIX))


# --- гейт run_check ---


def test_run_check_valid_file_exit_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Гейт: файл с валидными органами -> 0; в выводе строки OK и итог IMMUNE."""
    path = tmp_path / "organs.yaml"
    organs = [
        {"name": "good-a", "license": "MIT", "mode": "dependency"},
        {"repo": "good/b", "license_pre": "CC0-1.0", "mode": "reference"},
    ]
    path.write_text(yaml.safe_dump({"organs": organs}, allow_unicode=True), encoding="utf-8")
    assert run_check([path]) == 0
    out = capsys.readouterr().out
    assert "OK " in out
    assert "IMMUNE: 2 ok, 0 failed" in out


def test_run_check_violation_exit_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Гейт: AGPL-3.0 + dependency (встраивание) -> 1 и FAIL в выводе."""
    path = tmp_path / "bad.yaml"
    organs = [
        {"name": "good", "license": "MIT", "mode": "dependency"},
        {"name": "bad", "license": "AGPL-3.0", "mode": "dependency"},
    ]
    path.write_text(yaml.safe_dump({"organs": organs}, allow_unicode=True), encoding="utf-8")
    assert run_check([path]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "IMMUNE: FAIL" in out


def test_run_check_broken_yaml_exit_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Повреждённый YAML или отсутствующий файл — вклад в отказ (fail-closed), код 1."""
    broken = tmp_path / "broken.yaml"
    broken.write_text("organs: [ {name: x, license: MIT\n", encoding="utf-8")
    assert run_check([broken]) == 1
    assert "FAIL" in capsys.readouterr().out
    assert run_check([tmp_path / "absent.yaml"]) == 1


# --- CLI ---


def test_cli_main_exit_codes(tmp_path: Path) -> None:
    """CLI main([...]): валидный файл -> 0, нарушающий -> 1; --matrix подменяет правила (G2)."""
    good = tmp_path / "good.yaml"
    good.write_text(
        yaml.safe_dump({"organs": [{"name": "a", "license": "MIT", "mode": "dependency"}]}, allow_unicode=True),
        encoding="utf-8",
    )
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        yaml.safe_dump({"organs": [{"name": "b", "license": "GPL-3.0", "mode": "adapter"}]}, allow_unicode=True),
        encoding="utf-8",
    )
    assert main([str(good)]) == 0
    assert main([str(bad)]) == 1

    custom = {"modes": MATRIX["modes"], "core_modes": MATRIX["core_modes"], "allowed": ["GPL-3.0"]}
    custom_path = tmp_path / "custom-matrix.yaml"
    custom_path.write_text(yaml.safe_dump(custom, allow_unicode=True), encoding="utf-8")
    assert main(["--matrix", str(custom_path), str(bad)]) == 0


# --- вердикт — неизменяемое значение ---


def test_decision_is_frozen() -> None:
    """Decision заморожен: правка поля после вынесения вердикта запрещена."""
    d = verdict("MIT", "dependency", MATRIX)
    assert isinstance(d, Decision)
    with pytest.raises(FrozenInstanceError):
        d.ok = False  # type: ignore[misc]
