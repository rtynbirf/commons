"""Тесты спайка S2: честность харнесса агентного цикла — цифры не выдумываются.

langchain на CI-машине может отсутствовать, и это норма: в таком мире харнесс
обязан печатать NO_LANGCHAIN (код 2), в мире с langchain — выдавать таблицу
замера (код 0). Тест зелёный в обоих мирах; сам замер задокументирован в
spikes/s2-cycle/README.md, а не подгоняется под код тестов.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MEASURE = "spikes/s2-cycle/measure.py"
README = REPO_ROOT / "spikes" / "s2-cycle" / "README.md"


def test_measure_is_honest_in_both_worlds() -> None:
    """Без langchain — NO_LANGCHAIN (код 2); с langchain — таблица замера (код 0)."""
    proc = subprocess.run(
        [sys.executable, MEASURE],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
    )
    if importlib.util.find_spec("langchain") is None:
        assert proc.returncode == 2, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        assert "NO_LANGCHAIN" in proc.stdout, f"нет честного отказа:\n{proc.stdout}"
    else:
        assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        rows = [
            line
            for line in proc.stdout.splitlines()
            if line.startswith("|") and "---" not in line and not line.startswith("| путь")
        ]
        assert len(rows) >= 3, f"в таблице меньше 3 строк замера:\n{proc.stdout}"


def test_measurement_is_documented_in_readme() -> None:
    """Замер зафиксирован в README спайка — таблица из прогона, не выдумка в коде."""
    text = README.read_text(encoding="utf-8")
    assert "langchain 1.x" in text, "в README нет строки замера langchain 1.x"
    assert "COMMONS ствол мозга" in text, "в README нет строки замера COMMONS"
