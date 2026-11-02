# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Страж полномочий — исполнение `authority` рантаймом (SPEC-0002 п.8): audit hook (один
на процесс, лениво) прерывает выход органа за заявленное AuthorityViolation на время
adapter.invoke. Грамматика исполнима (normalize), ось без значения = самая строгая
(fail-closed), непарсабельное охраняемое событие — запрет (fail-closed).
"""

from __future__ import annotations

import ipaddress
import os
import sys
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, NamedTuple

FS_VALUES = ("none", "read-only", "read-write")
NETWORK_LABELS = ("none", "localhost", "any")
PROCESS_VALUES = ("none", "spawn")
_STRICT: dict[str, Any] = {"fs": "none", "network": "none", "process": "none"}
_AXIS_VALUES = {"fs": FS_VALUES, "process": PROCESS_VALUES}
_FS_MUTATIONS = frozenset({"os.remove", "os.rename", "os.mkdir", "os.rmdir", "os.chmod", "os.chown"})
_GUARDED = frozenset({"open", "socket.connect", "socket.bind", "socket.getaddrinfo", "subprocess.Popen"}) | _FS_MUTATIONS
_WRITE_MODE_CHARS = frozenset("wax+")
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT


class AuthorityViolation(RuntimeError):
    """Орган превысил полномочия — страж прервал вызов (SPEC-0002 п.8)."""


class AuthorityConfigError(ValueError):
    """Грамматика authority не исполнима — манифест не валиден, шлюз не стартует (SPEC-0002 п.8)."""


class Guard(NamedTuple):
    organ: str
    authority: dict[str, Any]


_ACTIVE: ContextVar[Guard | None] = ContextVar("commons-authority-guard", default=None)
_local = threading.local()  # флаг «уже внутри решения» — защита от рекурсии
_hook_lock, _hook_installed, _runtime_roots = threading.Lock(), False, None


def normalize(authority: Any, organ: str | None = None) -> dict[str, Any]:
    """Грамматика authority -> dict со всеми тремя осями; None = все `none`; кривая грамматика — AuthorityConfigError."""
    if authority is None:
        return dict(_STRICT)  # fail-closed: ось без значения = самый строгий вариант
    if not isinstance(authority, dict):
        raise AuthorityConfigError(_where(organ, f"authority должен быть dict, а не {type(authority).__name__}"))
    out = dict(_STRICT)
    for axis, value in authority.items():
        allowed = _AXIS_VALUES.get(axis) if isinstance(axis, str) else None
        if allowed and value in allowed:
            out[axis] = value
        elif allowed:
            raise AuthorityConfigError(_where(organ, f"{axis}: неизвестное значение {value!r} (допустимо: {', '.join(allowed)})"))
        elif axis == "network":
            out["network"] = _normalize_network(value, organ)
        else:
            raise AuthorityConfigError(_where(organ, f"неизвестная ось {axis!r} (оси: fs, network, process)"))
    return out


@contextmanager
def enforce(authority: dict, organ: str = "-"):
    """Активирует страж на время вызова органа; вложенность поддержана (восстанавливает прежнего)."""
    guard = Guard(organ, authority)
    token = _ACTIVE.set(guard)
    try:
        _install_hook()
        yield guard
    finally:
        _ACTIVE.reset(token)


def _where(organ: str | None, text: str) -> str:
    return f"орган {organ!r}: {text}" if organ else text


def _normalize_network(value: Any, organ: str | None) -> Any:
    if isinstance(value, str) and value in NETWORK_LABELS:
        return value
    if isinstance(value, dict) and set(value) == {"hosts"}:
        hosts = value["hosts"]
        if isinstance(hosts, list) and hosts and all(isinstance(h, str) and h.strip() for h in hosts):
            return {"hosts": list(hosts)}
        raise AuthorityConfigError(_where(organ, "network: hosts — непустой список непустых строк"))
    raise AuthorityConfigError(_where(organ, f"network: неизвестное значение {value!r} (допустимо: none, localhost, any или {{hosts: [...]}})"))


def _install_hook() -> None:
    """Один audit hook на процесс: лениво при первом enforce, идемпотентно, потокобезопасно."""
    global _hook_installed
    if _hook_installed:
        return
    with _hook_lock:
        if _hook_installed:
            return
        sys.addaudithook(_hook)
        _hook_installed = True


def _hook(event: str, args: tuple) -> None:
    guard = _ACTIVE.get()
    if guard is None or event not in _GUARDED:
        return  # страж неактивен или событие не охраняемо — накладные ~наносекунды
    if getattr(_local, "deciding", False):
        return  # решение не порождает решений (защита от рекурсии)
    _local.deciding = True
    try:
        _check(guard, event, args)
    finally:
        _local.deciding = False


def _check(guard: Guard, event: str, args: tuple) -> None:
    try:
        if event == "open":
            _check_open(guard, args)
        elif event in _FS_MUTATIONS:
            fs = guard.authority.get("fs", "none")
            if fs != "read-write":
                raise AuthorityViolation(_text(guard, event, f"fs: {fs}", "мутация файловой системы запрещена"))
        elif event.startswith("socket."):
            _check_socket(guard, event, args)
        elif (process := guard.authority.get("process", "none")) != "spawn":
            raise AuthorityViolation(_text(guard, "subprocess.Popen", f"process: {process}", "создание процессов запрещено"))
    except AuthorityViolation:
        raise
    except Exception as exc:  # кривые args: событие охраняемое — fail-closed (SPEC-0002 G1)
        raise AuthorityViolation(_text(guard, event, "fail-closed", f"событие не разобрано: {type(exc).__name__}: {exc}")) from None


def _text(guard: Guard, event: str, rule: str, detail: str) -> str:
    return f"орган {guard.organ!r}: {event} {detail} — нарушено заявленное правило ({rule})"


def _check_open(guard: Guard, args: tuple) -> None:
    path = args[0] if args else None
    mode = args[1] if len(args) > 1 else None
    flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
    fs = guard.authority.get("fs", "none")
    writing = (isinstance(mode, str) and _WRITE_MODE_CHARS.intersection(mode)) or bool(flags & _WRITE_FLAGS)
    if writing and fs != "read-write":
        raise AuthorityViolation(_text(guard, "open", f"fs: {fs}", f"запись запрещена: {path!r} (режим {mode!r})"))
    if not writing and fs == "none" and not _under_python_runtime(path):
        raise AuthorityViolation(_text(guard, "open", "fs: none", f"чтение запрещено (кроме рантайма Python): {path!r}"))


def _under_python_runtime(path: Any) -> bool:
    """Чтение рантайма Python (интерпретатор, stdlib) разрешено и при fs: none — иначе орган не жив."""
    global _runtime_roots
    if not isinstance(path, (str, bytes)) or not path:
        return False
    if _runtime_roots is None:
        bases = {os.path.abspath(os.fsdecode(b)) for b in (sys.base_prefix, sys.prefix, sys.exec_prefix) if b}
        bases.add(os.path.dirname(os.path.abspath(os.fsdecode(sys.executable))))
        _runtime_roots = tuple(sorted((b + os.sep for b in bases), key=len, reverse=True))
    clean = os.path.abspath(os.fsdecode(path))
    return any(clean.startswith(root) or clean + os.sep == root for root in _runtime_roots)


def _check_socket(guard: Guard, event: str, args: tuple) -> None:
    net = guard.authority.get("network", "none")
    if net == "any":
        return
    host = _socket_host(event, args)
    if isinstance(host, bytes):
        host = os.fsdecode(host)
    if not _host_allowed(net, host):
        rule = f"network: hosts {net.get('hosts')}" if isinstance(net, dict) else f"network: {net}"
        raise AuthorityViolation(_text(guard, event, rule, f"адрес вне полномочий: {host!r}"))


def _socket_host(event: str, args: tuple) -> Any:
    """Хост события: connect/bind — args[1] (адрес), getaddrinfo — args[0]; None = не разобран."""
    if event == "socket.getaddrinfo":
        return args[0] if args else None
    if len(args) > 1 and isinstance(args[1], tuple) and args[1]:
        return args[1][0]
    if len(args) > 1 and isinstance(args[1], (str, bytes)):
        return args[1]  # unix-сокет: путь
    return None


def _host_allowed(net: Any, host: Any) -> bool:
    """none — всё запрещено; localhost — loopback и имя localhost; {hosts} — точное имя; непарсабельное — запрет."""
    if host is None:
        return False
    if net == "localhost":
        try:
            return (isinstance(host, str) and host.lower() == "localhost") or ipaddress.ip_address(host).is_loopback
        except (ValueError, TypeError):
            return False
    return isinstance(net, dict) and isinstance(host, str) and host.lower() in {h.lower() for h in (net.get("hosts") or [])}
