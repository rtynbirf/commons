# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмки волны №25 — законы при конфликте (W-0036), гейт дрейфа аксиом (W-0034) и честный ADR транспорта (Ф-3.1).

W-0036 (дыра ревизии 2026-11-03 «нет приоритета при конфликте законов»):
живые случаи уже были — стыки волн (выметание параллельной машины против
сохранения пролитой крови), тишина против вечного ожидания (ADR-0015),
append-only против выметания. Порядок законов обязан быть назван ЗАРАНЕЕ,
по-записанному, а не решаться по настроению момента. Матрица живёт данными
(docs/axioms.yaml), вердикт — ADR-0016; гейт доктора не даёт им разъехаться.

W-0034 (хотёлка «гейт дрейфа аксиом»): матрица пакета A01–A25 (ревизия
2026-11-03) — живой документ дома, а не строка в пролитой крови. Живая
матрица — docs/axioms.yaml с указателями на доказательства (тесты, спеки,
ADR); доктор сверяет матрицу с домом так же, как сверяет версии и хотёлки:
битый вердикт, несуществующий указатель, дубликат ID — блоха, fail-closed.

Ф-3.1 (ТЗ ревизора): MCP HTTP-транспорт + OAuth 2.1 — или честный ADR
«только stdio». Дом выбирает честный ADR-0017: тело не имеет каналов
(SPEC-0010), наружу — donation и патчи, не транспорт.
"""
from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("doctor", REPO_ROOT / "scripts" / "doctor.py")
doctor = importlib.util.module_from_spec(_spec)
sys.modules["doctor"] = doctor
_spec.loader.exec_module(doctor)

AXIOMS = REPO_ROOT / "docs" / "axioms.yaml"
ADR16 = REPO_ROOT / "docs" / "adr" / "ADR-0016-lex-priority.md"
ADR17 = REPO_ROOT / "docs" / "adr" / "ADR-0017-stdio-only.md"

VERDICTS = {"pass", "partial", "served", "adr", "open"}


# --- W-0034: живая матрица аксиом ---


def test_axioms_matrix_exists_and_complete() -> None:
    """Матрица существует, содержит ровно A01–A25 без дублей и пропусков."""
    data = yaml.safe_load(AXIOMS.read_text(encoding="utf-8"))
    ids = [a["id"] for a in data["axioms"]]
    expected = [f"A{i:02d}" for i in range(1, 26)]
    assert ids == expected, f"матрица обязана быть полной и по порядку: {ids}"


def test_axioms_verdicts_in_vocabulary() -> None:
    """Вердикт каждой аксиомы — из словаря дома, незнакомое — блоха."""
    data = yaml.safe_load(AXIOMS.read_text(encoding="utf-8"))
    for axiom in data["axioms"]:
        assert axiom["verdict"] in VERDICTS, f"{axiom['id']}: чужой вердикт {axiom['verdict']!r}"


def test_axioms_evidence_exists_on_disk() -> None:
    """Каждый указатель доказательства жив на диске: мёртвый указатель — фантазия."""
    data = yaml.safe_load(AXIOMS.read_text(encoding="utf-8"))
    for axiom in data["axioms"]:
        for rel in axiom.get("evidence", []):
            assert (REPO_ROOT / rel).exists(), f"{axiom['id']}: указатель {rel} ведёт в пустоту"


def test_open_axioms_name_the_plan() -> None:
    """Открытая и частичная аксиома обязана называть план (где закрывается)."""
    data = yaml.safe_load(AXIOMS.read_text(encoding="utf-8"))
    revision = REPO_ROOT / "runs" / "2026-11-03-revision" / "REVISION.md"
    assert revision.exists()
    for axiom in data["axioms"]:
        if axiom["verdict"] in {"open", "partial"}:
            assert axiom.get("plan"), f"{axiom['id']}: открытая аксиома без плана — обман"


def test_laws_priority_named_and_unique() -> None:
    """Порядок законов назван заранее: непустой, без дублей."""
    data = yaml.safe_load(AXIOMS.read_text(encoding="utf-8"))
    laws = data["laws_priority"]
    assert isinstance(laws, list) and len(laws) >= 3
    names = [law["name"] for law in laws]
    assert len(names) == len(set(names)), "закон дважды на одной ступени — не матрица"


def test_laws_priority_honesty_first_safety_second() -> None:
    """Живой случай дома: честность выше безопасности в том смысле, что
    лжёт дом — это самый дорогой провал; безопасность — fail-closed.
    Порядок в матрице обязан сохранять эти два наверху без инверсии."""
    data = yaml.safe_load(AXIOMS.read_text(encoding="utf-8"))
    names = [law["name"] for law in data["laws_priority"]]
    assert names[0] == "честность"
    assert names[1] == "безопасность"


# --- W-0036: ADR-0016 — матрица приоритета законов ---


def test_adr16_exists_and_names_every_law() -> None:
    """ADR-0016 существует и называет ровно те законы, что в матрице данных."""
    text = ADR16.read_text(encoding="utf-8")
    data = yaml.safe_load(AXIOMS.read_text(encoding="utf-8"))
    for law in data["laws_priority"]:
        assert law["name"] in text, f"ADR-0016 не называет закон {law['name']!r}"


def test_adr16_names_lived_conflicts() -> None:
    """ADR обязан держать живые случаи дома, иначе это фантазия, не закон."""
    text = ADR16.read_text(encoding="utf-8")
    for marker in ("Стыки волн", "ADR-0015", "append-only"):
        assert marker in text, f"ADR-0016 не называет живой случай: {marker!r}"


def test_adr16_tie_rule_is_junction_not_coin_flip() -> None:
    """При равном законе — «одно другое не исключает» (обе линии служат,
    стык сшивает), не подбрасывание монеты."""
    text = ADR16.read_text(encoding="utf-8")
    assert "одно другое не исключает" in text


# --- Ф-3.1: ADR-0017 — честный ADR «только stdio» ---


def test_adr17_declares_stdio_only() -> None:
    """Ф-3.1 разрешена честным ADR: только stdio, HTTP+OAuth отклонены."""
    text = ADR17.read_text(encoding="utf-8")
    assert "stdio" in text
    assert "OAuth" in text


def test_adr17_honors_no_channels_body() -> None:
    """Решение обязано держать тело без каналов (SPEC-0010) и называть границу."""
    text = ADR17.read_text(encoding="utf-8")
    assert "SPEC-0010" in text
    assert "аудience" in text.lower() or "audience" in text.lower(), "граница OAuth audience-binding обязана быть названа"


def test_manifest_transport_default_is_stdio() -> None:
    """Данные не противоречат ADR: транспорт по умолчанию — stdio."""
    manifest = yaml.safe_load((REPO_ROOT / "synapse" / "mcp-manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["transport_default"] == "stdio"


# --- гейт доктора `axioms` (W-0034) ---


def test_doctor_has_axioms_gate_and_live_house_is_clean() -> None:
    """Гейт существует и на живом доме зелёный."""
    names = [name for name, _ in doctor.GATES]
    assert "axioms" in names
    ok, fleas = doctor.check_axioms(REPO_ROOT)
    assert ok == len(yaml.safe_load(AXIOMS.read_text(encoding="utf-8"))["axioms"]), fleas
    assert fleas == [], fleas


def _copy_house(tmp_path: Path) -> Path:
    dst = tmp_path / "house"
    shutil.copytree(REPO_ROOT, dst, ignore=shutil.ignore_patterns("__pycache__", ".git", "*.pyc"))
    return dst


def test_axioms_gate_catches_unknown_verdict(tmp_path: Path) -> None:
    """Чужой вердикт — блоха (fail-closed)."""
    house = _copy_house(tmp_path)
    axioms = house / "docs" / "axioms.yaml"
    # бьём по строке аксиомы (4 пробела), а не по заголовочному комментарию
    axioms.write_text(
        axioms.read_text(encoding="utf-8").replace("\n    verdict: pass", "\n    verdict: якобы-ок", 1),
        encoding="utf-8",
    )
    ok, fleas = doctor.check_axioms(house)
    assert ok == 24 and fleas and "чужой вердикт" in fleas[0]


def test_axioms_gate_catches_missing_evidence(tmp_path: Path) -> None:
    """Вердикт «served» без доказательства — обман, не вердикт."""
    house = _copy_house(tmp_path)
    axioms = house / "docs" / "axioms.yaml"
    # A01 (первая аксиома с evidence) теряет доказательства — served остаётся без пробы
    axioms.write_text(
        axioms.read_text(encoding="utf-8").replace("\n    evidence:", "\n    evidence: []\n    evidence_legacy:", 1),
        encoding="utf-8",
    )
    ok, fleas = doctor.check_axioms(house)
    assert fleas and "без доказательства" in fleas[0] and ok < 25


def test_axioms_gate_fail_closed_on_unparseable(tmp_path: Path) -> None:
    """Нечитаемый yaml — красный без суждения, не зелёный."""
    house = _copy_house(tmp_path)
    (house / "docs" / "axioms.yaml").write_text("::: сломано :::\n", encoding="utf-8")
    ok, fleas = doctor.check_axioms(house)
    assert ok == 0 and fleas and "не читается" in fleas[0]


def test_axioms_gate_catches_incomplete_matrix(tmp_path: Path) -> None:
    """Матрица короче A25 — блоха: тишина не значит «всё хорошо»."""
    house = _copy_house(tmp_path)
    data = yaml.safe_load((house / "docs" / "axioms.yaml").read_text(encoding="utf-8"))
    data["axioms"] = [a for a in data["axioms"] if a["id"] != "A25"]
    (house / "docs" / "axioms.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    ok, fleas = doctor.check_axioms(house)
    assert ok == 24 and fleas and "A25" in fleas[0]
