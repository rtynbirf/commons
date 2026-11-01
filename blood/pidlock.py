"""Одиночность организма (SPEC-0004 п.2, G6): файловый lock с pid владельца.

Живой владелец → LockHeld (второй организм получает veto).
Протухший lock (владелец мёртв) заменяется — тело не остаётся запертым за мёртвым.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


class LockHeld(RuntimeError):
    """Организм уже жив: второй экземпляр в то же тело не входит."""


def _alive(pid: int) -> bool:
    """Жив ли процесс: os.kill(pid, 0) — разведка без выстрела."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # процесс чужой, но живой
    return True


class PIDLock:
    """Файл-замок: json {pid, ts}. Захват атомарный (O_CREAT|O_EXCL)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._acquired = False

    def acquire(self) -> int:
        """Захватывает lock. Возвращает pid владельца (наш).

        Второй раз тем же экземпляром не вызывается; протухший lock
        (владелец мёртв) заменяется одной попыткой.
        """
        for _ in (1, 2):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                pid = self._holder_pid()
                if pid is not None and _alive(pid):
                    raise LockHeld(f"PID {pid} (lock {self.path})") from None
                # владелец мёртв или lock нечитаем — тело не запирают за мёртвыми
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "pid": os.getpid(),
                    "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "path": str(self.path),
                }, ensure_ascii=False))
            self._acquired = True
            return os.getpid()
        raise LockHeld(f"не удалось захватить lock {self.path}")

    def _holder_pid(self) -> int | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return int(data["pid"])
        except (OSError, ValueError, KeyError, TypeError):
            return None  # нечитаемый lock = протухший

    def release(self) -> None:
        """Освобождает lock — только свой (чужой не трогаем)."""
        if not self._acquired:
            return
        if self._holder_pid() == os.getpid():
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
        self._acquired = False
