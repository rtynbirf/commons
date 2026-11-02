# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмка SPEC-0002 v0.9.0 «защита в глубину и граница R1» (волна №13 такт 2).

Слой поверх их ядерной песочницы (0.31.0, SPEC-0002 v0.8.0 п.11): находки волны №13
фиксируются приёмками —
- U1: UDP sendto — не audit-событие Python (страж слеп), ронято их фильтром (socket inet → EPERM)
  ДО кода детёныша — язык не важен;
- C13: ctypes libc.socket — raw-syscall вне audit-грамматики, ронято тем же фильтром —
  защита в глубину: audit hook не единственная граница;
- R1 (приёмка-предписание): детёныш соединяется по УНАСЛЕДОВАННОМУ дескриптору
  (создан до стража, передан pass_fds) raw-connect'ом — их фильтр не роняет connect,
  страж слеп к raw-syscall: соединение проходит, в крови обычный act. Граница названа,
  не закрыта: приёмка ПОКРАСНЕЕТ, когда ядерная граница научится ронять connect по
  унаследованному fd (deny connect сломает unix-connect — граница; или гигиена pass_fds
  под стражем) — как приёмка волны №10 покраснела волной №12 по предписанию.

Свидетель — живой TCP/UDP-сервер на loopback.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

from synapse.authority import AuthorityViolation, enforce

REPO_ROOT = Path(__file__).resolve().parent.parent


def _sandbox_scope() -> dict:
    return {
        "fs": "read-only",
        "network": "none",
        "process": {
            "mode": "spawn",
            "programs": [Path(sys.executable).name, "curl", "sh"],
            "sandbox": {"network": "none"},
        },
    }


@contextmanager
def witness(kind: str = "tcp") -> Iterator[tuple[int, list[str]]]:
    """Живой свидетель: TCP-сервер (соединения) или UDP-сервер (дейтаграммы)."""
    stype = socket.SOCK_STREAM if kind == "tcp" else socket.SOCK_DGRAM
    srv = socket.socket(socket.AF_INET, stype)
    srv.bind(("127.0.0.1", 0))
    if kind == "tcp":
        srv.listen(4)
    port = srv.getsockname()[1]
    hits: list[str] = []
    stop = threading.Event()

    def serve() -> None:
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                if kind == "tcp":
                    conn, _ = srv.accept()  # type: ignore[union-attr]
                    with conn:
                        try:
                            conn.recv(64)
                        except OSError:
                            pass
                        hits.append("tcp")
                else:
                    srv.recvfrom(64)  # type: ignore[union-attr]
                    hits.append("udp")
            except (socket.timeout, OSError):
                continue

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield port, hits
    finally:
        stop.set()
        thread.join(timeout=2)
        srv.close()


# --- a) чужой бинарник под песочницей: живой TCP-свидетель ----------------------------


def test_curl_under_sandbox_blocked() -> None:
    """curl (чужой бинарник) под sandbox не соединяется: EPERM от ядра, свидетель чист (п.11)."""
    with witness("tcp") as (port, hits):
        with enforce(_sandbox_scope(), organ="w13b-curl"):
            proc = subprocess.run(
                ["curl", "--max-time", "2", "-s", f"http://127.0.0.1:{port}/"],
                capture_output=True, text=True, timeout=20,
            )
    assert hits == [], f"свидетель видел соединений: {len(hits)}"
    assert proc.returncode != 0, "curl обязан не соединиться"


def test_network_free_program_alive() -> None:
    """Заявленная программа без сети жива под песочницей: граница не рвёт безсетевых (п.11)."""
    with enforce(_sandbox_scope(), organ="w13b-version"):
        proc = subprocess.run(["curl", "--version"], capture_output=True, text=True, timeout=20)
    assert proc.returncode == 0 and "curl" in proc.stdout, proc.stderr[-160:]


# --- b) находка U1: UDP sendto — вне audit-грамматики, ронято ядром --------------------


def test_udp_sendto_denied() -> None:
    """U1: socket(AF_INET, SOCK_DGRAM) — тот же inet-socket, ядро рвёт до кода детёныша."""
    with witness("udp") as (port, hits):
        code = (
            "import socket\n"
            f"s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)\n"
            f"s.sendto(b'leak', ('127.0.0.1', {port}))\n"
            "print('UDP-LEAKED')\n"
        )
        with enforce(_sandbox_scope(), organ="w13b-udp"):
            proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=20)
    assert "UDP-LEAKED" not in proc.stdout, f"дейтаграмма ушла: {proc.stdout!r}"
    assert hits == [], f"свидетель видел дейтаграмм: {len(hits)}"
    assert proc.returncode != 0, "socket(AF_INET, DGRAM) обязан быть ронят EPERM'ом"


# --- c) находка C13: ctypes raw-syscall — ронято ядром (защита в глубину) --------------


def test_ctypes_raw_socket_denied() -> None:
    """C13: libc.socket через ctypes — audit hook'у нечего перехватывать, ядро рвёт."""
    with witness("tcp") as (port, hits):
        code = (
            "import ctypes, socket, struct\n"
            "libc = ctypes.CDLL('libc.so.6', use_errno=True)\n"
            f"sa = struct.pack('HH4s8s', 2, socket.htons({port}), bytes([127, 0, 0, 1]), b'\\x00' * 8)\n"
            "fd = libc.socket(2, 1, 0)  # AF_INET, SOCK_STREAM\n"
            "if fd < 0:\n"
            "    print('SOCKET-EPERM')\n"
            "else:\n"
            "    print('LEAKED' if libc.connect(fd, sa, len(sa)) == 0 else 'CONNECT-EPERM')\n"
        )
        with enforce(_sandbox_scope(), organ="w13b-ctypes"):
            proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=20)
    assert "LEAKED" not in proc.stdout, f"raw-syscall соединился: {proc.stdout!r}"
    assert hits == [], f"свидетель видел соединений: {len(hits)}"
    assert "SOCKET-EPERM" in proc.stdout or "CONNECT-EPERM" in proc.stdout, proc.stdout


# --- d) находка R1: унаследованный дескриптор — приёмка-предписание ---------------------


def test_inherited_fd_boundary_prescription() -> None:
    """R1: детёныш соединяется по унаследованному fd raw-connect'ом — и фильтр, и страж слепы.
    СЕГОДНЯ соединение проходит (дыра жива) — приёмка зелёная как предписание; ПОКРАСНЕЕТ,
    когда граница R1 закрыта (гигиена pass_fds под стражем или deny connect — с честным
    названием unix-границы), тогда перевернуть, как волна №12 перевернула С3 (v0.9.0)."""
    with witness("tcp") as (port, hits):
        leak_fd = socket.socket()  # создан ДО стража: родитель под network: none его не открывал
        fd = leak_fd.fileno()
        code = (
            "import ctypes, os, socket, struct\n"
            f"sa = struct.pack('HH4s8s', 2, socket.htons({port}), bytes([127, 0, 0, 1]), b'\\x00' * 8)\n"
            "libc = ctypes.CDLL('libc.so.6', use_errno=True)\n"
            "rc = libc.connect(int(os.environ['LEAK_FD']), sa, len(sa))\n"
            "print('FD-LEAKED' if rc == 0 else 'FD-BLOCKED')\n"
        )
        with enforce(_sandbox_scope(), organ="w13b-inherited"):
            proc = subprocess.run(
                [sys.executable, "-c", code], capture_output=True, text=True, timeout=20,
                pass_fds=(fd,), env=dict(os.environ, LEAK_FD=str(fd)),
            )
        leak_fd.close()
    assert "FD-LEAKED" in proc.stdout, (
        "соединение по унаследованному fd перестало проходить — граница R1 закрыта: "
        "переверни эту приёмку и честно назови новое поведение (v0.9.0)"
    )
    assert len(hits) == 1, f"свидетель обязан видеть ровно одно (унаследованное) соединение: {len(hits)}"


# --- e) граница действия: без sandbox сеть детёныша — дело хоста (их приёмка, контроль) --


def test_no_sandbox_spawn_untouched() -> None:
    """spawn без sandbox — прежняя граница: рождение без ядерного фильтра не прерано (п.11)."""
    scope = {"fs": "read-only", "network": "none", "process": "spawn"}
    with enforce(scope, organ="w13b-nosandbox"):
        proc = subprocess.run([sys.executable, "-c", "print('FREE')"], capture_output=True, text=True, timeout=20)
    assert proc.returncode == 0 and "FREE" in proc.stdout
