# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0

"""Приёмка иммунного гейта (волна 0.7.0): живое тело организма чисто.

Гейт в CI прогоняет реальные synapse/mcp-manifest.yaml и organs/registry.yaml
через лицензионную матрицу immune: политика уже соблюдена — теперь она контракт.
Ветчины иммунитета: veto на copyleft/NOASSERTION/fair-code в ядре (dependency,
adapter), G1 fail-closed на незнакомую лицензию в ядре, rule='missing' на пустые
поля, битый YAML не проходит молча, каждый вердикт объясним (rule + reason).
"""

from __future__ import annotations

import io
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
import yaml

from immune.barrier import Decision, check_entries, load_matrix, run_check, verdict

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_MANIFEST = REPO_ROOT / "synapse" / "mcp-manifest.yaml"
REAL_REGISTRY = REPO_ROOT / "organs" / "registry.yaml"

# Снимок тела на момент гейта: 36 органов в реестре (+4 в манифесте = 40 OK гейта).
# Рост реестра — осознанная правка этого числа в том же коммите, что и новые органы.
REGISTRY_SNAPSHOT_ORGANS = 36

# Человеческая политика, выраженная данными: copyleft/неопределённые лицензии
# не встраиваются в ядро — только external/reference/substrate/education.
NO_EMBED_LICENSES = {
    "AGPL-3.0",
    "GPL-3.0",
    "GPL-2.0",
    "NOASSERTION",
    "fair-code (Sustainable Use)",
    "по-навыковые (ToU Anthropic)",
}
EMBED_MODES = {"dependency", "adapter"}

# Полный словарь правил контракта; правил-сюрпризов в живом теле быть не должно.
KNOWN_RULES = {
    "allowed",
    "conditional",
    "restricted",
    "unrecognized",
    "fail-closed",
    "missing",
    "unknown-mode",
}
SURPRISE_RULES = {"unrecognized", "fail-closed"}


# --- Оснастка ---


@pytest.fixture()
def matrix() -> dict:
    """Пакетная лицензионная матрица immune."""
    return load_matrix()


def load_organs(path: Path) -> list[dict]:
    """Органы из реального YAML-файла (dict с ключом 'organs')."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data["organs"]


def organ_name(entry: dict) -> str:
    """Имя органа: name в манифесте, repo в реестре."""
    return entry.get("name") or entry.get("repo") or ""


def organ_license(entry: dict) -> str:
    """Лицензия органа: license в манифесте, license_pre в реестре."""
    return entry.get("license") or entry.get("license_pre") or ""


def tainted_manifest(tmp_path: Path, organ: dict) -> Path:
    """Копия реального манифеста с одним подсаженным органом (safe_load -> append -> safe_dump)."""
    data = yaml.safe_load(REAL_MANIFEST.read_text(encoding="utf-8"))
    data["organs"].append(organ)
    path = tmp_path / "manifest-tainted.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def gate(paths: list[Path]) -> tuple[int, str]:
    """Прогон гейта с перехватом вывода (код + текст)."""
    out = io.StringIO()
    code = run_check(paths, out=out)
    return code, out.getvalue()


# --- Живое тело чисто: реальные файлы проходят гейт ---


def test_manifest_clean(matrix) -> None:
    """Реальный манифест синапсов: run_check == 0 и каждая запись ok (в том числе через check_entries)."""
    code, text = gate([REAL_MANIFEST])
    assert code == 0
    assert "IMMUNE: 5 ok, 0 failed" in text
    decisions = check_entries(load_organs(REAL_MANIFEST), matrix)
    assert len(decisions) == 5
    for d in decisions:
        assert d.ok, f"{d.organ}: {d.rule} — {d.reason}"


def test_registry_clean(matrix) -> None:
    """Реальный реестр: снимок тела, run_check == 0, все ok — политика уже соблюдена, теперь она контракт."""
    entries = load_organs(REAL_REGISTRY)
    assert len(entries) == REGISTRY_SNAPSHOT_ORGANS
    code, text = gate([REAL_REGISTRY])
    assert code == 0
    assert "0 failed" in text
    decisions = check_entries(entries, matrix)
    assert len(decisions) == len(entries)
    assert all(d.ok for d in decisions), [
        f"{d.organ}: {d.rule} — {d.reason}" for d in decisions if not d.ok
    ]


def test_registry_full_coverage(matrix) -> None:
    """Матрица явно описывает весь живой спектр: ни одной пары (license_pre, mode) с правилом-сюрпризом."""
    for entry in load_organs(REAL_REGISTRY):
        d = verdict(
            license=organ_license(entry),
            mode=entry["mode"],
            matrix=matrix,
            organ=organ_name(entry),
        )
        assert d.rule not in SURPRISE_RULES, f"{d.organ}: {d.rule} — {d.reason}"
        assert d.ok


def test_copyleft_never_embedded() -> None:
    """Человеческая политика данными: copyleft/NOASSERTION/fair-code не встраивается (dependency/adapter)."""
    embedded = []
    for entry in load_organs(REAL_REGISTRY):
        if entry.get("license_pre") in NO_EMBED_LICENSES:
            if entry["mode"] in EMBED_MODES:
                embedded.append(f"{organ_name(entry)}: {entry['license_pre']} в режиме {entry['mode']}")
    assert not embedded, f"встраивание запрещённых лицензий: {embedded}"


# --- Иммунный ответ: подсаженные органы получают veto ---


def test_veto_agpl_dependency_rejected(tmp_path: Path) -> None:
    """AGPL-3.0 в ядре (dependency): run_check -> 1, вывод содержит FAIL и имя органа."""
    path = tainted_manifest(tmp_path, {"name": "malicious-organ", "license": "AGPL-3.0", "mode": "dependency"})
    code, text = gate([path])
    assert code == 1
    assert "FAIL" in text
    assert "malicious-organ" in text
    summary = next(line for line in text.splitlines() if line.startswith("IMMUNE:"))
    assert "FAIL" in summary and "5 ok" in summary and "1 failed" in summary


def test_veto_noassertion_dependency_rejected(tmp_path: Path) -> None:
    """NOASSERTION (лицензия не определена) в ядре — тот же veto: -> 1."""
    path = tainted_manifest(tmp_path, {"name": "noassertion-organ", "license": "NOASSERTION", "mode": "dependency"})
    code, text = gate([path])
    assert code == 1
    assert "FAIL" in text
    assert "noassertion-organ" in text


# --- G1: fail-closed и молчаливые отказы невозможны ---


def test_fail_closed_unknown_license_dependency(tmp_path: Path, matrix) -> None:
    """Незнакомая лицензия в ядре (dependency): -> 1 по правилу fail-closed (G1)."""
    entry = {"name": "custom-organ", "license": "My-Custom-License", "mode": "dependency"}
    path = tainted_manifest(tmp_path, entry)
    code, text = gate([path])
    assert code == 1
    assert "FAIL" in text
    decisions = check_entries([entry], matrix)
    assert not decisions[0].ok
    assert decisions[0].rule == "fail-closed"


def test_fail_closed_corrupted_yaml(tmp_path: Path) -> None:
    """Битый YAML не проходит молча: ошибка чтения/парсинга -> 1."""
    path = tmp_path / "corrupted.yaml"
    path.write_text("organs: [ {", encoding="utf-8")
    code, text = gate([path])
    assert code == 1


def test_missing_fields_rejected(tmp_path: Path, matrix) -> None:
    """Запись без license: run_check -> 1, check_entries даёт rule='missing'."""
    entry = {"name": "headless-organ", "mode": "dependency"}
    path = tainted_manifest(tmp_path, entry)
    code, text = gate([path])
    assert code == 1
    decisions = check_entries([entry], matrix)
    assert len(decisions) == 1
    assert not decisions[0].ok
    assert decisions[0].rule == "missing"
    assert decisions[0].reason


# --- Гейт как его зовёт CI ---


def test_manifest_and_registry_in_one_gate() -> None:
    """Оба реальных файла одним прогоном: run_check -> 0 (ровно так зовёт CI)."""
    code, text = gate([REAL_MANIFEST, REAL_REGISTRY])
    assert code == 0
    assert "IMMUNE:" in text
    assert "0 failed" in text


def test_decisions_carry_rule_and_reason(matrix) -> None:
    """Каждый вердикт реального реестра объясним: непустые rule и reason, rule из словаря контракта."""
    entries = load_organs(REAL_REGISTRY)
    decisions = check_entries(entries, matrix)
    assert len(decisions) == len(entries)
    for entry, d in zip(entries, decisions):
        assert isinstance(d, Decision)
        assert d.rule in KNOWN_RULES, f"{d.organ}: неизвестное правило {d.rule!r}"
        assert d.rule
        assert d.reason
        assert d.license == organ_license(entry)
        assert d.organ == organ_name(entry)
    with pytest.raises(FrozenInstanceError):
        decisions[0].ok = not decisions[0].ok  # Decision иммутабелен: вердикт не переписать
