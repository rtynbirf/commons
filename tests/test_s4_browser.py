"""Тесты спайка S4: структура scenarios.yaml и офлайн-честность run.py.

Живой прогон харнесса требует браузерного MCP-сервера — на CI его нет, и это
норма: здесь проверяется только то, что харнесс не врёт. Структурная валидность
сценариев (--validate, код 0) и отказ вместо выдуманных цифр без браузера
(NO_BROWSER, код 2). Оба пути работают офлайн на любой машине.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN = REPO_ROOT / "spikes" / "s4-browser" / "run.py"
SCENARIOS = REPO_ROOT / "spikes" / "s4-browser" / "scenarios.yaml"


def _load_run():
    """Импортирует run.py как модуль: каталог s4-browser с дефисом напрямую не импортируется."""
    spec = importlib.util.spec_from_file_location("s4_browser_run", RUN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_real_scenarios_yaml_is_valid() -> None:
    """Реальный scenarios.yaml структурно валиден — самопроверка харнесса ему доверяет."""
    s4_run = _load_run()
    scenarios = yaml.safe_load(SCENARIOS.read_text(encoding="utf-8"))["scenarios"]
    assert s4_run.validate_scenarios(scenarios) == [], "реальный набор сценариев сломан"


def test_broken_set_reports_each_kind() -> None:
    """Сломанный инлайн-набор ловится по всем видам: дубль id, шаг, limit, pass."""
    s4_run = _load_run()
    broken = [
        {"id": "S4-01", "goal": "цель", "steps": ["navigate"], "pass": "критерий", "limit": 30},
        {"id": "S4-01", "goal": "дубль", "steps": ["fly"], "pass": "", "limit": 0},
    ]
    errors = s4_run.validate_scenarios(broken)
    assert len(errors) >= 4, f"ожидались ошибки всех видов, получено: {errors}"
    report = "\n".join(errors)
    for field in ("id", "steps", "limit"):
        assert field in report, f"в отчёте нет упоминания {field}:\n{report}"


def test_validate_flag_is_offline_green() -> None:
    """--validate на реальном файле: код 0 и OK — браузер не требуется."""
    proc = subprocess.run(
        [sys.executable, "spikes/s4-browser/run.py", "--validate"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert "OK" in proc.stdout, f"нет подтверждения валидности:\n{proc.stdout}"


def test_no_browser_refuses_to_invent() -> None:
    """Честность: заведомо отсутствующая команда на PATH → NO_BROWSER и код 2."""
    proc = subprocess.run(
        [sys.executable, "spikes/s4-browser/run.py", "--command", "commons-no-such-browser-cmd"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 2, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert "NO_BROWSER" in proc.stdout, f"нет отказа вместо выдумки:\n{proc.stdout}"
