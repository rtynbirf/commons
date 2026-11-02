# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Живые органы волны №13 (ядерная песочница детёнышей): честный пробник и живой свидетель.

- LiveProber — орган-пробник: invoke("run_argv", {argv}) запускает заявленную программу
  и возвращает её stdout (детёныш честно отчитывается, что ядро ему разрешило или отказало).
- ControlServer — живой свидетель волны №10 (переиспользован без дубликатов): настоящий
  HTTP на loopback, счётчик соединений — для контрольной сцены без песочницы.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from blood.envelope import Cost

_RED_ORGANS = Path(__file__).resolve().parent.parent / "2026-11-02-wave10-red-run-live" / "red_organs.py"
_spec = importlib.util.spec_from_file_location("w10_red_organs", _RED_ORGANS)
assert _spec and _spec.loader, f"арена №10 не найдена: {_RED_ORGANS}"
_mod = importlib.util.module_from_spec(_spec)
sys.modules["w10_red_organs"] = _mod
_spec.loader.exec_module(_mod)

ControlServer = _mod.ControlServer  # живой свидетель: счётчик настоящих соединений


class LiveProber:
    """Орган-пробник: рождает детёныша по argv и возвращает его stdout — факт, не интерпретация."""

    def __init__(self, entry: dict[str, Any]) -> None:
        self.entry = entry

    def health(self) -> bool:
        return True

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Cost]:
        if tool != "run_argv":
            raise AssertionError(f"неизвестный инструмент {tool!r}")
        started = time.monotonic()
        proc = subprocess.run(payload["argv"], capture_output=True, text=True, timeout=30)
        return (
            {"stdout": proc.stdout.strip(), "returncode": proc.returncode},
            Cost(tokens_in=len(str(payload)), tokens_out=len(proc.stdout), seconds=round(time.monotonic() - started, 3)),
        )
