"""Приёмка такта аудита (волна №30-такт, 0.48.2) — сверка реестра с машиной.

Косяк, пойманный аудитом 2026-11-03 живым замером: волны №28–№29 докладывали
счёт A-матрицы «СЛУЖЕНО/PASS 23 · красных 1 (A21)», а живой реестр
``docs/axioms.yaml`` давал 21/3 — статусы A19/A20 (служены волной №28:
маркеры живы в свидетелях, приёмки живы) не были перевёрнуты в реестре.
Гейт axioms проверял только направление «СЛУЖЕНО → маркер жив» и не проверял
обратное; счёт книг никто не сверял — коммит-сообщение обогнало реестр.

Выметено: статусы A19/A20 перевёрнуты по факту (since 0.47.0, witness, marker);
порог DoD этапа (СЛУЖЕНО/PASS ≥ 20, красных ≤ 2 — docs/TZ.md §4) держит гейт
axioms; книгам запрещено дублировать счёт A-матрицы в статике — число живёт
в реестре, число в книге протухает.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "doctor.py"
TZ = REPO_ROOT / "docs" / "TZ.md"
PERSONAS = REPO_ROOT / "docs" / "personas.md"


def _doctor():
    """Доктор загружается на каждый вызов: гейта ещё нет — AttributeError
    красит приёмку честно (красный прогон на нетронутом коде)."""
    spec = importlib.util.spec_from_file_location("doctor_wave30", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["doctor_wave30"] = module
    spec.loader.exec_module(module)
    return module


# --- порог DoD держит машина ---


def _registry_rows(red_ids: list[str]) -> list[dict]:
    rows: list[dict] = []
    for i in range(1, 26):
        aid = f"A{i:02d}"
        if aid == "A01":
            rows.append(
                {
                    "id": aid,
                    "title": "повтор ключа — тот же исход",
                    "status": "СЛУЖЕНО",
                    "witness": "tests/test_witness.py",
                    "marker": "маркер служения",
                }
            )
        elif aid in red_ids:
            rows.append(
                {
                    "id": aid,
                    "title": "красная строка",
                    "status": "НЕ СЛУЖЕНО",
                    "todo": "ТЗ-2.3",
                }
            )
        else:
            rows.append({"id": aid, "title": "строка", "status": "СЛУЖЕНО", "witness": ""})
    return rows


def test_dod_threshold_red_on_excess_red(tmp_path: Path) -> None:
    """Отставший реестр (служеные аксиомы остались красными) превышает лимит
    красных — гейт красит поимённо, как поймал такт аудита (живой дом давал
    красных 3 > 2 до переворота A19/A20)."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_witness.py").write_text("маркер служения жив\n", encoding="utf-8")
    # A02–A04 красные (3 > 2) + все СЛУЖЕНО без свидетеля — посторонние блохи
    # допустимы, порог обязан прозвучать независимо от них.
    rows = _registry_rows(red_ids=["A02", "A03", "A04"])
    (docs / "axioms.yaml").write_text(
        yaml.dump({"axioms": rows}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    ok, fleas = _doctor().check_axioms(tmp_path)
    assert ok == 0
    assert any("порог DoD нарушен — красных 3 > 2" in f for f in fleas), fleas


def test_dod_threshold_red_on_missing_served(tmp_path: Path) -> None:
    """Порог по СЛУЖЕНО/PASS тоже живой: меньше 20 — красное."""
    docs = tmp_path / "docs"
    docs.mkdir()
    rows = _registry_rows(red_ids=[f"A{i:02d}" for i in range(2, 26)])
    (docs / "axioms.yaml").write_text(
        yaml.dump({"axioms": rows}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    ok, fleas = _doctor().check_axioms(tmp_path)
    assert ok == 0
    assert any("порог DoD нарушен — СЛУЖЕНО/PASS 1 < 20" in f for f in fleas), fleas


def test_dod_threshold_green_on_house() -> None:
    """Живой дом после переворота реестра: порог DoD не звучит —
    СЛУЖЕНО/PASS ≥ 20, красных ≤ 2 (красная одна: A21, ТЗ-2.3)."""
    ok, fleas = _doctor().check_axioms(REPO_ROOT)
    threshold = [f for f in fleas if "порог DoD" in f]
    assert threshold == [], threshold


# --- счёт A-матрицы не дублируется в статике книг ---


def test_books_do_not_duplicate_axiom_count(tmp_path: Path) -> None:
    """Счёт A-матрицы в книге — протухатель в двух живых формах, обе пойманы
    тактом аудита: «(сейчас 23…)» в TZ и «СЛУЖЕНО/PASS 23 + СНЯТО 1…» в
    ROADMAP. Порог формулируется со знаком (≥/≤) — он живёт в книгах."""
    docs = tmp_path / "docs"
    docs.mkdir()
    rows = _registry_rows(red_ids=[])
    (docs / "axioms.yaml").write_text(
        yaml.dump({"axioms": rows}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    tz = tmp_path / "docs" / "TZ.md"
    tz.write_text(
        "# ТЗ\n\nA-матрица: СЛУЖЕНО/PASS ≥ 20 из 25 (сейчас 23 после волн), красных ≤ 2.\n",
        encoding="utf-8",
    )
    roadmap = tmp_path / "ROADMAP.md"
    roadmap.write_text(
        "# Карта\n\n- A-матрица: СЛУЖЕНО/PASS 23 + СНЯТО 1 (A17) · НЕ СЛУЖЕНО 1 (A21) — порог взят.\n",
        encoding="utf-8",
    )
    ok, fleas = _doctor().check_axioms(tmp_path)
    assert ok == 0
    assert any("docs/TZ.md:3: книга дублирует счёт A-матрицы" in f for f in fleas), fleas
    assert any("ROADMAP.md:3: книга дублирует счёт A-матрицы" in f for f in fleas), fleas


def test_threshold_wording_with_sign_is_not_a_flea(tmp_path: Path) -> None:
    """Порог DoD (критерий ≥/≤) в книге — не счёт: красить нельзя,
    иначе гейт запрещает книгам называть собственный критерий."""
    docs = tmp_path / "docs"
    docs.mkdir()
    rows = _registry_rows(red_ids=[])
    (docs / "axioms.yaml").write_text(
        yaml.dump({"axioms": rows}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    tz = tmp_path / "docs" / "TZ.md"
    tz.write_text(
        "# ТЗ\n\nA-матрица: СЛУЖЕНО/PASS ≥ 20 из 25, красных ≤ 2 — порог держит гейт.\n",
        encoding="utf-8",
    )
    _ok, fleas = _doctor().check_axioms(tmp_path)
    assert not any("дублирует счёт" in f for f in fleas), fleas


def test_house_books_do_not_duplicate_axiom_count() -> None:
    """Живые книги счёт не дублируют — граница жанров стоит в доме."""
    ok, fleas = _doctor().check_axioms(REPO_ROOT)
    duplicates = [f for f in fleas if "дублирует счёт A-матрицы" in f]
    assert duplicates == [], duplicates


# --- факт аудита кредов вписан в W-0004 ---


def test_w0004_records_credential_audit_fact() -> None:
    """Такт аудита замерил креды живым API: смерть токена волн №27–№29
    подтверждена (401), следующий токен жив (200, login=rtynbirf).
    Факт обязан жить в W-0004; сами значения токенов — нет (гейт secrets)."""
    text = PERSONAS.read_text(encoding="utf-8")
    start = text.index("### W-0004")
    end = text.index("### W-", start + 1)
    body = text[start:end]
    assert "смерть токена волн №27–№29 подтверждена живым API — 401" in body
    assert "следующий токен проверен живым API — 200" in body
    assert "им доставлен такт аудита 0.48.2" in body
    assert "ghp_" not in body, "значение токена в книги не пишется (гейт secrets)"
