"""Приёмка харнесса спайка S6: матрица офлайн, честная базовая линия sqlite3, NO_ENGINE.

Все тесты зелёные без установки движков: базовая линия sqlite3 (stdlib) работает
всегда; если chromadb не установлен, харнесс обязан печатать NO_ENGINE (код 2),
а не притворяться замером (тест 5 — зелёный в обоих мирах).
"""

from __future__ import annotations

import importlib.util
import math
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MEASURE = REPO_ROOT / "spikes" / "s6-memory" / "measure.py"

_spec = importlib.util.spec_from_file_location("s6_measure", MEASURE)
assert _spec is not None and _spec.loader is not None
s6 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s6)


def test_matrix_offline_lists_candidates() -> None:
    """Режим --matrix офлайн: exit 0, в выводе есть кандидаты sqlite-vec, chroma, qdrant."""
    result = subprocess.run(
        [sys.executable, "spikes/s6-memory/measure.py", "--matrix"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "sqlite-vec" in result.stdout
    assert "chroma" in result.stdout
    assert "qdrant" in result.stdout


def test_baseline_bench_prints_numbers_without_flags() -> None:
    """Без флагов — как --bench: exit 0, базовая линия sqlite3 с числами замера."""
    result = subprocess.run(
        [sys.executable, "spikes/s6-memory/measure.py"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "sqlite3" in result.stdout
    assert re.search(r"insert \d", result.stdout), result.stdout
    assert re.search(r"query \d", result.stdout), result.stdout


def test_cosine_unit() -> None:
    """Юнит: cosine — сонаправленные 1, ортогональные 0, противоположные -1."""
    assert math.isclose(s6.cosine([1.0, 0.0], [1.0, 0.0]), 1.0, abs_tol=1e-9)
    assert math.isclose(s6.cosine([1.0, 0.0], [0.0, 1.0]), 0.0, abs_tol=1e-9)
    assert math.isclose(s6.cosine([1.0, 0.0], [-1.0, 0.0]), -1.0, abs_tol=1e-9)


def test_make_vectors_deterministic_and_normalized() -> None:
    """Юнит: одинаковый seed → равные списки; каждый вектор нормализован (|v|≈1)."""
    first = s6.make_vectors(10, 8, seed=42)
    second = s6.make_vectors(10, 8, seed=42)
    assert first == second
    for vector in first:
        norm = math.sqrt(math.fsum(x * x for x in vector))
        assert math.isclose(norm, 1.0, abs_tol=1e-9)


def test_chroma_engine_is_measured_or_honestly_refused() -> None:
    """Честность: chromadb не установлен → NO_ENGINE, код 2; установлен → замер, код 0."""
    result = subprocess.run(
        [sys.executable, "spikes/s6-memory/measure.py", "--bench", "--engine", "chroma"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    if importlib.util.find_spec("chromadb") is None:
        assert result.returncode == 2, result.stdout + result.stderr
        assert "NO_ENGINE" in result.stdout
    else:
        assert result.returncode == 0, result.stdout + result.stderr
