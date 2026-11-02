# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмка SPEC-0002 v0.10.0 «гигиена дескрипторов и рождения мимо обёртки» (волна №14).

Находки волны №14, обе живые:
- R1 (названа волной №13, приёмка-предписание): детёныш соединяется по УНАСЛЕДОВАННОМУ
  дескриптору (создан до стража, передан `pass_fds`) raw-connect'ом — фильтр роняет
  `socket()`, не `connect` по существующему fd, страж слеп к raw-syscall. ЗАКРЫТА: гигиена
  дескрипторов под стражем — сокет-дескриптор в `pass_fds`, stdio-перенаправлениях или
  `close_fds=False` (наследует весь стол) при `network` ≠ `any` — `AuthorityViolation` ДО
  создания процесса (unix-граница честно названа: дескриптор = capability мимо грамматики,
  гранулярность S_ISSOCK — домены fstat не различает); питоновский детёныш с просочившимся
  fd не живёт — сам-скан на старте (exit 90, fail-closed).
- R2 (новая, живая разведка): `os.posix_spawn` и `os.system` — audit-события существуют,
  но страж их не охранял — рождение мимо обёртки Popen: конверт не передаётся (args
  неизменяемы), декларация не проверялась, в крови обычный `act`. ПЕРЕВЕРНУТА:
  `os.system` — всегда нарушение (строка shell не разбираем — fail-closed, как
  `shell: True` со скоупом), `os.posix_spawn` — декларация исполняется (программа из
  заявленных, max_children), при `network` ≠ `any` рождение прервано (детёныш без конверта
  был бы С3-ренегатом).

Свидетель — живой TCP-сервер на loopback: считает каждое настоящее соединение.
"""

from __future__ import annotations

import json
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

SPAWN_NET_NONE = {"fs": "read-only", "network": "none", "process": "spawn"}


@contextmanager
def witness() -> Iterator[tuple[int, list[str]]]:
    """Живой свидетель: слушает loopback, считает каждое принятое соединение."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    port = srv.getsockname()[1]
    hits: list[str] = []
    stop = threading.Event()

    def serve() -> None:
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
            except (socket.timeout, OSError):
                continue
            with conn:
                try:
                    conn.recv(64)
                except OSError:
                    pass
                hits.append("hit")

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield port, hits
    finally:
        stop.set()
        thread.join(timeout=2)
        srv.close()


def _raw_connect_code(port: int) -> str:
    """raw-connect по существующему fd — то, что не ронят ни фильтр (socket()), ни страж."""
    return (
        "import ctypes, os, socket, struct\n"
        f"sa = struct.pack('HH4s8s', 2, socket.htons({port}), bytes([127, 0, 0, 1]), b'\\x00' * 8)\n"
        "libc = ctypes.CDLL('libc.so.6', use_errno=True)\n"
        "rc = libc.connect(int(os.environ['LEAK_FD']), sa, len(sa))\n"
        "print('FD-LEAKED' if rc == 0 else 'FD-BLOCKED')\n"
    )


# --- a) R1 закрыта: сокет-дескриптор в pass_fds не проходит -------------------------


def test_socket_pass_fd_denied_at_birth() -> None:
    """Сокет-fd в pass_fds при network: none — рождение прервано ДО создания процесса
    (гигиена дескрипторов, v0.10.0); свидетель чист; unix-граница названа в тексте."""
    with witness() as (port, hits):
        leak_fd = socket.socket()  # создан ДО стража — как в красном прогоне волны №13
        fd = leak_fd.fileno()
        code = _raw_connect_code(port)
        with enforce({"fs": "read-only", "network": "none", "process": {"mode": "spawn", "programs": [Path(sys.executable).name]}}):
            with pytest.raises(AuthorityViolation) as exc_info:
                subprocess.run(
                    [sys.executable, "-c", code], capture_output=True, text=True, timeout=20,
                    pass_fds=(fd,), env=dict(os.environ, LEAK_FD=str(fd)),
                )
        leak_fd.close()
    text = str(exc_info.value)
    assert "дескриптор" in text and "сокет" in text, f"текст не называет границу: {text!r}"
    assert "network: none" in text, f"текст не называет заявленное правило: {text!r}"
    assert hits == [], f"свидетель видел соединений: {len(hits)} — R1 не закрыта"


def test_socket_pass_fd_alive_under_network_any() -> None:
    """network: any — capability заявлена: дескриптор проходит, raw-connect жив
    (гигиена не рвёт заявленное; seccomp не ставился — фильтра нет)."""
    scope = {"fs": "read-only", "network": "any", "process": {"mode": "spawn", "programs": [Path(sys.executable).name]}}
    with witness() as (port, hits):
        leak_fd = socket.socket()
        fd = leak_fd.fileno()
        code = _raw_connect_code(port)
        with enforce(scope, organ="w14-any"):
            proc = subprocess.run(
                [sys.executable, "-c", code], capture_output=True, text=True, timeout=20,
                pass_fds=(fd,), env=dict(os.environ, LEAK_FD=str(fd)),
            )
        leak_fd.close()
    assert "FD-LEAKED" in proc.stdout, f"raw-connect не должен был быть прерван: {proc.stdout!r} {proc.stderr[-200:]!r}"
    assert len(hits) == 1, f"свидетель обязан видеть ровно одно соединение: {len(hits)}"


def test_socket_pass_fd_denied_under_localhost() -> None:
    """network: localhost — fd тоже прерван: connect по унаследованному fd не несёт хоста,
    грамматика хостов его не проверяет — capability мимо грамматики (честно)."""
    scope = {"fs": "read-only", "network": "localhost", "process": {"mode": "spawn", "programs": [Path(sys.executable).name]}}
    leak_fd = socket.socket()
    fd = leak_fd.fileno()
    with enforce(scope, organ="w14-localhost"):
        with pytest.raises(AuthorityViolation) as exc_info:
            subprocess.run(
                [sys.executable, "-c", "print('BORN')"], capture_output=True, text=True, timeout=20,
                pass_fds=(fd,),
            )
    leak_fd.close()
    assert "дескриптор" in str(exc_info.value)


def test_socket_stdio_redirect_denied() -> None:
    """stdio-перенаправление на сокет-fd — тот же канал: детёныш пишет в сеть fd'ом.
    Прервано до рождения (v0.10.0)."""
    leak_fd = socket.socket()
    fd = leak_fd.fileno()
    with enforce(dict(SPAWN_NET_NONE), organ="w14-stdio"):
        with pytest.raises(AuthorityViolation) as exc_info:
            subprocess.run(
                [sys.executable, "-c", "print('BORN')"], capture_output=False, timeout=20,
                stdout=fd,
            )
    leak_fd.close()
    text = str(exc_info.value)
    assert "дескриптор" in text and "сокет" in text, f"текст не называет границу: {text!r}"


def test_close_fds_false_socket_inheritance_denied() -> None:
    """close_fds=False наследует весь стол дескрипторов — при живых сокетах и network: none
    рождение прервано (живой скан /proc/self/fd)."""
    extra = socket.socket()  # лишний сокет в родителе — детёныш унаследовал бы его целиком
    try:
        with enforce(dict(SPAWN_NET_NONE), organ="w14-closefds"):
            with pytest.raises(AuthorityViolation) as exc_info:
                subprocess.run(
                    [sys.executable, "-c", "print('BORN')"], capture_output=True, text=True,
                    timeout=20, close_fds=False,
                )
    finally:
        extra.close()
    text = str(exc_info.value)
    assert "close_fds" in text and "сокет" in text.lower(), f"текст не называет канал: {text!r}"


def test_pipe_pass_fd_alive() -> None:
    """Пайп в pass_fds жив — гигиена рвёт только сокеты, передача не-сетевых fd не сломана."""
    r, w = os.pipe()
    try:
        with enforce(dict(SPAWN_NET_NONE), organ="w14-pipe"):
            proc = subprocess.run(
                [sys.executable, "-c", "print('PIPED')"], capture_output=True, text=True,
                timeout=20, pass_fds=(w,),
            )
    finally:
        os.close(r)
        os.close(w)
    assert proc.returncode == 0 and "PIPED" in proc.stdout, f"пайп не должен был мешать: {proc.stderr[-200:]!r}"


# --- b) детёныш не живёт с просочившимся сокет-дескриптором (сам-скан, exit 90) ------

def _envelope_env(authority: dict) -> dict[str, str]:
    env = dict(os.environ)
    env["COMMONS_AUTHORITY"] = json.dumps({"organ": "leaked-child", "authority": authority})
    env["PYTHONPATH"] = str(REPO_ROOT)
    return env


def test_child_self_scan_refuses_leaked_fd() -> None:
    """Питоновский детёныш с просочившимся сокет-fd не живёт: сам-скан на старте —
    exit 90 до первого оператора (fail-closed, защита в глубину: даже мимо обёртки)."""
    leak_fd = socket.socket()
    fd = leak_fd.fileno()
    try:
        proc = subprocess.run(
            [sys.executable, "-c", "print('CHILD_ALIVE')"],
            capture_output=True, text=True, timeout=20,
            pass_fds=(fd,), env=_envelope_env(SPAWN_NET_NONE),
        )
    finally:
        leak_fd.close()
    assert proc.returncode == 90, f"детёныш обязан не жить (exit 90): rc={proc.returncode} err={proc.stderr[-200:]!r}"
    assert "CHILD_ALIVE" not in proc.stdout, "детёныш с чужим сокетом поработал"


def test_child_without_leak_alive() -> None:
    """Контроль: тот же конверт без чужих сокетов — детёныш жив (сам-скан не рвёт обычных)."""
    proc = subprocess.run(
        [sys.executable, "-c", "print('CHILD_ALIVE')"],
        capture_output=True, text=True, timeout=20, env=_envelope_env(SPAWN_NET_NONE),
    )
    assert proc.returncode == 0 and "CHILD_ALIVE" in proc.stdout, f"обычный детёныш не должен был умереть: {proc.stderr[-200:]!r}"


# --- c) R2 перевернута: рождения мимо обёртки под охраной ---------------------------


def test_posix_spawn_denied_when_process_none() -> None:
    """os.posix_spawn при process: none — рождение прервано (audit-событие есть — страж смотрит)."""
    with enforce({"fs": "read-only", "network": "none", "process": "none"}, organ="w14-posix-none"):
        with pytest.raises(AuthorityViolation) as exc_info:
            os.posix_spawn("/bin/true", ["/bin/true"], {})
    assert "создание процессов запрещено" in str(exc_info.value), str(exc_info.value)


def test_posix_spawn_denied_under_scope_network_none() -> None:
    """os.posix_spawn под скоупом и network: none — тоже прерван, но по честной причине R2:
    конверт не передаётся (args неизменяемы) — детёныш жил бы без стража (С3-ренегат)."""
    scope = {"fs": "read-only", "network": "none", "process": {"mode": "spawn", "programs": ["true"]}}
    with enforce(scope, organ="w14-posix-scope"):
        with pytest.raises(AuthorityViolation) as exc_info:
            os.posix_spawn("/bin/true", ["/bin/true"], {})
    text = str(exc_info.value)
    assert "мимо обёртки" in text and "конверт" in text, f"текст не называет причину R2: {text!r}"


def test_posix_spawn_alive_under_network_any() -> None:
    """os.posix_spawn при network: any и заявленной программе — жив (декларация исполнена)."""
    scope = {"fs": "read-only", "network": "any", "process": {"mode": "spawn", "programs": ["true"]}}
    with enforce(scope, organ="w14-posix-any"):
        pid = os.posix_spawn("/bin/true", ["/bin/true"], dict(os.environ))
        _, status = os.waitpid(pid, 0)
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0, f"/bin/true обязан выйти 0: {status}"


def test_posix_spawn_undeclared_program_denied() -> None:
    """os.posix_spawn вне заявленных программ — рождение прервано до факта (декларация)."""
    scope = {"fs": "read-only", "network": "any", "process": {"mode": "spawn", "programs": ["true"]}}
    with enforce(scope, organ="w14-posix-decl"):
        with pytest.raises(AuthorityViolation) as exc_info:
            os.posix_spawn("/bin/false", ["/bin/false"], {})
    assert "вне заявленных программ" in str(exc_info.value), str(exc_info.value)


def test_os_system_denied_always() -> None:
    """os.system — строка shell не разбираем: нарушение при process: none и при скоупе
    (fail-closed, как shell: True со скоупом, v0.7.0)."""
    with enforce({"fs": "read-only", "network": "any", "process": "none"}, organ="w14-sys-none"):
        with pytest.raises(AuthorityViolation):
            os.system("true")
    scope = {"fs": "read-only", "network": "any", "process": {"mode": "spawn", "programs": ["true"]}}
    with enforce(scope, organ="w14-sys-scope"):
        with pytest.raises(AuthorityViolation) as exc_info:
            os.system("true")
    assert "shell" in str(exc_info.value).lower(), str(exc_info.value)
