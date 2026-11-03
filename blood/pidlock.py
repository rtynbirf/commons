"""Одиночность организма (SPEC-0004 п.2, G6): файловый lock с pid владельца.

Живой владелец → LockHeld (второй организм получает veto).
Протухший lock заменяется — тело не остаётся запертым за мёртвым.

0.4.0 (W-0031, волна №26, ТЗ-0.5): владелец — процесс, а не номер.
Разведка os.kill(pid, 0) различает «жив ли кто-то с этим номером», но не
«кто» — гипотеза F-12 коллег (2026-11-03) подтверждена живьём: зомби
(мёртвый процесс, которого ещё не пожинали) держал lock, LockHeld живому
телу; после аварии и reиспользования pid чужой живой процесс считался бы
владельцем. Свидетель — стартовое время процесса (поле 22
/proc/<pid>/stat): lock обслуживается, только если состояние не Z и время
совпадает с записанным. /proc нет (чужая граница) — fallback по kill(0),
граница названа в спеке, не скрыта. Старый lock без start_time валиден:
зомби ловится состоянием, reиспользование на старом формате не различимо —
старые lock-файлы не переписываются задним числом.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


class LockHeld(RuntimeError):
    """Организм уже жив: второй экземпляр в то же тело не входит."""


def _stat_fields(pid: int, proc_root: str) -> list[str] | None:
    """Поля /proc/<pid>/stat после comm: state (бывш. поле 3) и далее."""
    try:
        raw = (Path(proc_root) / str(pid) / "stat").read_text(encoding="utf-8")
    except OSError:
        return None
    tail = raw.rpartition(")")[2].split()
    return tail or None


def _start_ticks(pid: int, proc_root: str = "/proc") -> str | None:
    """Стартовое время процесса (поле 22 stat, тики от загрузки) строкой.

    Поле 22 файла: после `pid (comm)` tail начинается с state (поле 3),
    значит starttime — tail[19]. Строкой, чтобы не терять точность.
    """
    tail = _stat_fields(pid, proc_root)
    if tail is None or len(tail) < 20:
        return None
    return tail[19]


def _holder_state(pid: int, proc_root: str) -> str | None:
    tail = _stat_fields(pid, proc_root)
    return tail[0] if tail else None


def _alive(pid: int, start_time: str | None = None, proc_root: str = "/proc") -> bool:
    """Жив ли владелец: тот же процесс, не зомби и не reиспользованный pid.

    os.kill(pid, 0) — разведка без выстрела; /proc/<pid>/stat — свидетель
    «кто именно»: состояние Z (зомби) — владелец мёртв (W-0031), чужое
    стартовое время — номер занят другим процессом (reиспользование).
    /proc недоступен — kill-семантика: различаем «жив ли кто-то с этим
    номером», не «кто» — граница названа (SPEC-0004 п.2), не скрыта.
    """
    state = _holder_state(pid, proc_root)
    if state is None:
        # /proc нет или процесс исчез: разведка без выстрела — старая граница
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # процесс чужой, но живой
        return True
    if state == "Z":
        return False  # зомби — мёртвый владелец (живой замер волны №26)
    if start_time:
        actual = _start_ticks(pid, proc_root)
        if actual is not None and actual != start_time:
            return False  # pid reиспользован — владелец другой
    return True


class PIDLock:
    """Файл-замок: json {pid, ts, path, start_time}. Захват атомарный
    (O_CREAT|O_EXCL). start_time — свидетель «тот же процесс», None при
    недоступном /proc (kill-семантика, граница SPEC-0004 п.2)."""

    def __init__(self, path: str | Path, proc_root: str = "/proc") -> None:
        self.path = Path(path)
        self.proc_root = proc_root
        self._acquired = False

    def acquire(self) -> int:
        """Захватывает lock. Возвращает pid владельца (наш).

        Второй раз тем же экземпляром не вызывается; протухший lock
        (владелец мёртв, зомби или чужой) заменяется одной попыткой.
        """
        for _ in (1, 2):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                holder_pid, holder_start = self._holder()
                if holder_pid is not None and _alive(holder_pid, holder_start, self.proc_root):
                    raise LockHeld(f"PID {holder_pid} (lock {self.path})") from None
                # владелец мёртв/зомби/чужой или lock нечитаем — тело не
                # запирают за мёртвыми и за чужаками
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
                    "start_time": _start_ticks(os.getpid(), self.proc_root),
                }, ensure_ascii=False))
            self._acquired = True
            return os.getpid()
        raise LockHeld(f"не удалось захватить lock {self.path}")

    def _holder(self) -> tuple[int | None, str | None]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return int(data["pid"]), data.get("start_time")
        except (OSError, ValueError, KeyError, TypeError):
            return None, None  # нечитаемый lock = протухший

    def release(self) -> None:
        """Освобождает lock — только свой (чужой не трогаем)."""
        if not self._acquired:
            return
        holder_pid, _ = self._holder()
        if holder_pid == os.getpid():
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
        self._acquired = False
