"""Раннер живого организма (SPEC-0004): человек запускает — человек убивает.

Запуск из корня репо:
  python3 scripts/pid1.py                      # интервал 30 c, бюджет 3600 c
  python3 scripts/pid1.py --interval 10 --max-beats 5
  python3 scripts/pid1.py --help

После установки пакета: `commons-pid1` (pyproject [project.scripts]).
Артефакты сессии: runs/<дата>-pid1/blood.jsonl + report-<trace_id>.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from brainstem.pid1 import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
