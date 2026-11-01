"""Харнесс спайка S5: офлайн-самопроверка «спека ↔ код» (docs/spikes.md S5).

Все тесты зелёные на машине без spec-kit: режим --spec-kit в этом окружении
обязан печатать NO_SPEC_KIT (код 2), а не притворяться замером.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MEASURE = REPO_ROOT / "spikes" / "s5-genome" / "measure.py"

_spec = importlib.util.spec_from_file_location("s5_measure", MEASURE)
assert _spec is not None and _spec.loader is not None
s5 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s5)


def test_selfcheck_runs_offline_and_reports() -> None:
    """Режим --selfcheck стабилен офлайн: exit 0, в выводе есть спеки и дрейф."""
    proc = subprocess.run(
        [sys.executable, "spikes/s5-genome/measure.py", "--selfcheck"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SPEC-0001" in proc.stdout
    assert "дрейф" in proc.stdout


def test_parse_spec_counts_contract_and_guarantees() -> None:
    """Юнит: парсер считает пункты Контракта и маркеры Гарантий без внешних зависимостей."""
    mini = textwrap.dedent("""\
        # SPEC-9999: Мини-спека для проверки парсера

        Статус: черновик · Версия: 0.0.1

        ## Назначение

        Проверка, что анатомия считается по формату дома.

        ## Контракт

        1. Первое требование.
        2. Второе требование.

        ## Гарантии

        - **G1 Первая.** Организм не врёт.
        - **G2 Вторая.** Каждое действие с ценой.
        """)
    parsed = s5.parse_spec(mini)
    assert parsed["contract_count"] == 2
    assert parsed["guarantees"] == ["G1", "G2"]


def test_real_spec0001_guarantees_found() -> None:
    """Харнесс находит G1..G3 в живом геноме: specs/SPEC-0001-brainstem-loop.md."""
    text = (REPO_ROOT / "specs" / "SPEC-0001-brainstem-loop.md").read_text(encoding="utf-8")
    assert "G1" in s5.extract_guarantee_ids(text)
    parsed = s5.parse_spec(text)
    assert parsed["guarantees"] == ["G1", "G2", "G3"]


def test_spec_kit_without_binary_is_honest(tmp_path: Path) -> None:
    """Пустой PATH → specify не находится → NO_SPEC_KIT, код 2 (никаких выдуманных цифр)."""
    empty_path = tmp_path / "empty-bin"
    empty_path.mkdir()
    env = {
        "PATH": str(empty_path),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "PYTHONUTF8": "1",  # стабильный utf-8 stdout независимо от локали CI
    }
    proc = subprocess.run(
        [sys.executable, str(MEASURE), "--spec-kit"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 2
    assert "NO_SPEC_KIT" in proc.stdout
