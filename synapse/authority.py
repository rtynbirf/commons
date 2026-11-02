# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Страж полномочий — исполнение `authority` рантаймом (SPEC-0002 п.8): audit hook (один
на процесс, лениво) прерывает выход органа за заявленное AuthorityViolation на время
adapter.invoke. Грамматика исполнима (normalize), ось без значения = самая строгая
(fail-closed), непарсабельное охраняемое событие — запрет (fail-closed). Скоупы (v0.5.0):
fs знает пути ({mode, paths}, realpath — симлинк-побег закрыт), network знает порты
({hosts, ports}, точное совпадение). Потоки (v0.6.0): поток, рождённый под стражем,
наследует его (обёртка Thread.start — полномочия связывают код органа, а не поток;
запись `__pycache__` ленивым импортом прерывается с предписанием прогреть импорты).
Ядерная песочница (v0.8.0, п.11): `sandbox: {network: none}` в скоупе — детёнышу до
execve ставится seccomp-BPF (socket(AF_INET/6) → EPERM) — inet закрыт ядром для
любого детёныша, включая не-python (граница волны №12 «чужой бинарник» перевернута).
Детёныши (v0.7.0): страж оборачивает subprocess.Popen — питоновский детёныш получает
конверт COMMONS_AUTHORITY и живёт под полномочиями органа (sitecustomize), скоуп
{mode: spawn, programs, max_children} декларирует рождение; execve роняет hook —
чужой бинарник конверта не читает, его syscalls не видны (честная граница).
"""

from __future__ import annotations

import ipaddress
import json
import os
import subprocess
import sys
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, NamedTuple

FS_VALUES = ("none", "read-only", "read-write")
NETWORK_LABELS = ("none", "localhost", "any")
PROCESS_VALUES = ("none", "spawn")
_STRICT: dict[str, Any] = {"fs": "none", "network": "none", "process": "none"}
_AXIS_VALUES = {"process": PROCESS_VALUES}  # fs обрабатывается целиком в _normalize_fs (ярлык или скоуп)
_FS_MUTATIONS = frozenset({"os.remove", "os.rename", "os.mkdir", "os.rmdir", "os.chmod", "os.chown"})
_GUARDED = frozenset({"open", "socket.connect", "socket.bind", "socket.getaddrinfo", "subprocess.Popen"}) | _FS_MUTATIONS
_WRITE_MODE_CHARS = frozenset("wax+")
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT
_PYCACHE_PRESCRIPTION = "ленивый импорт внутри invoke пишет __pycache__ — прогрейте импорты до вызова (SPEC-0002 п.8)"
ACTIVE_ENV = "COMMONS_AUTHORITY"  # конверт полномочий детёныша (SPEC-0002 п.8, v0.7.0)


class AuthorityViolation(RuntimeError):
    """Орган превысил полномочия — страж прервал вызов (SPEC-0002 п.8)."""


class AuthorityConfigError(ValueError):
    """Грамматика authority не исполнима — манифест не валиден, шлюз не стартует (SPEC-0002 п.8)."""


class Guard(NamedTuple):
    organ: str
    authority: dict[str, Any]


_ACTIVE: ContextVar[Guard | None] = ContextVar("commons-authority-guard", default=None)
_local = threading.local()  # флаг «уже внутри решения» + счётчик детёнышей вызова
_hook_lock, _hook_installed, _runtime_roots = threading.Lock(), False, None
_thread_wrap_installed = False
_popen_wrap_installed = False
_repo_root_cached: str | None = None


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
        elif axis == "process":
            out["process"] = _normalize_process(value, organ)
        elif axis == "network":
            out["network"] = _normalize_network(value, organ)
        elif axis == "fs":
            out["fs"] = _normalize_fs(value, organ)
        else:
            raise AuthorityConfigError(_where(organ, f"неизвестная ось {axis!r} (оси: fs, network, process)"))
    return out


def _normalize_process(value: Any, organ: str | None) -> Any:
    """Ярлык или скоуп {mode: spawn, programs, max_children}: программы — имена без пути,
    max_children — целое >= 1 (SPEC-0002 п.8, v0.7.0)."""
    if isinstance(value, str) and value in PROCESS_VALUES:
        return value
    if isinstance(value, dict) and "mode" in value and "programs" in value:
        if value["mode"] != "spawn":
            raise AuthorityConfigError(_where(organ, "process: скоуп допустим только с mode: spawn (mode: none — ярлык без программ)"))
        extra = set(value) - {"mode", "programs", "max_children", "sandbox"}
        if extra:
            raise AuthorityConfigError(_where(organ, f"process: неизвестные ключи {sorted(extra)} (допустимо: mode, programs, max_children, sandbox)"))
        programs = value["programs"]
        if (not isinstance(programs, list) or not programs
                or not all(isinstance(p, str) and p.strip() and p.strip() == p
                           and os.path.basename(p) == p and p not in (".", "..") for p in programs)):
            raise AuthorityConfigError(_where(organ, "process: programs — непустой список имён программ без разделителей пути"))
        out: dict[str, Any] = {"mode": "spawn", "programs": [p.strip() for p in programs]}
        if "max_children" in value:
            limit = value["max_children"]
            if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
                raise AuthorityConfigError(_where(organ, "process: max_children — целое >= 1"))
            out["max_children"] = limit
        if "sandbox" in value:
            sandbox = value["sandbox"]
            if not (isinstance(sandbox, dict) and set(sandbox) == {"network"} and sandbox["network"] == "none"):
                raise AuthorityConfigError(_where(organ, 'process: sandbox — единственная исполнимая форма {network: none} (частичная сеть честно не исполнена, SPEC-0002 п.11)'))
            out["sandbox"] = {"network": "none"}
        return out
    raise AuthorityConfigError(_where(organ, f"process: неизвестное значение {value!r} (допустимо: none, spawn или {{mode: spawn, programs: [...], max_children: N}})"))


@contextmanager
def enforce(authority: dict, organ: str = "-"):
    """Активирует страж на время вызова органа; вложенность поддержана (восстанавливает прежнего)."""
    guard = Guard(organ, authority)
    token = _ACTIVE.set(guard)
    _local.spawned = 0  # счётчик детёнышей этого вызова (max_children, v0.7.0)
    try:
        _install_hook()
        yield guard
    finally:
        _ACTIVE.reset(token)


def _where(organ: str | None, text: str) -> str:
    return f"орган {organ!r}: {text}" if organ else text


def _normalize_fs(value: Any, organ: str | None) -> Any:
    """Ярлык или скоуп {mode, paths}: пути — непустой список абсолютных строк (SPEC-0002 п.8, v0.5.0)."""
    if isinstance(value, str) and value in FS_VALUES:
        return value
    if isinstance(value, dict) and set(value) == {"mode", "paths"}:
        mode, paths = value["mode"], value["paths"]
        if mode not in FS_VALUES:
            raise AuthorityConfigError(_where(organ, f"fs: неизвестный режим {mode!r} (допустимо: {', '.join(FS_VALUES)})"))
        if (not isinstance(paths, list) or not paths
                or not all(isinstance(p, str) and p.strip() and os.path.isabs(p) for p in paths)):
            raise AuthorityConfigError(_where(organ, "fs: paths — непустой список абсолютных путей"))
        return {"mode": mode, "paths": list(paths)}
    raise AuthorityConfigError(_where(organ, f"fs: неизвестное значение {value!r} (допустимо: none, read-only, read-write или {{mode, paths}})"))


def _normalize_network(value: Any, organ: str | None) -> Any:
    if isinstance(value, str) and value in NETWORK_LABELS:
        return value
    if isinstance(value, dict) and set(value) in ({"hosts"}, {"hosts", "ports"}):
        hosts = value["hosts"]
        if not (isinstance(hosts, list) and hosts and all(isinstance(h, str) and h.strip() for h in hosts)):
            raise AuthorityConfigError(_where(organ, "network: hosts — непустой список непустых строк"))
        if "ports" in value:
            ports = value["ports"]
            if (not isinstance(ports, list) or not ports
                    or not all(isinstance(p, int) and not isinstance(p, bool) and 1 <= p <= 65535 for p in ports)):
                raise AuthorityConfigError(_where(organ, "network: ports — непустой список целых 1..65535 (порт 0 и эфемерные не заявляемы)"))
            return {"hosts": list(hosts), "ports": list(ports)}
        return {"hosts": list(hosts)}
    raise AuthorityConfigError(_where(organ, f"network: неизвестное значение {value!r} (допустимо: none, localhost, any или {{hosts: [...]}})"))


def _install_hook() -> None:
    """Один audit hook на процесс + наследование стража потоками и детёнышами: лениво
    при первом enforce, идемпотентно, потокобезопасно (SPEC-0002 п.8, v0.6.0/v0.7.0)."""
    global _hook_installed, _thread_wrap_installed, _popen_wrap_installed
    if _hook_installed and _thread_wrap_installed and _popen_wrap_installed:
        return
    with _hook_lock:
        if not _hook_installed:
            sys.addaudithook(_hook)
            _hook_installed = True
        if not _thread_wrap_installed:
            _install_thread_inheritance()
        if not _popen_wrap_installed:
            _install_popen_inheritance()


def _install_thread_inheritance() -> None:
    """Поток, рождённый под стражем, наследует его (v0.6.0): обёртка Thread.start — один
    раз на процесс, идемпотентно. Полномочия связывают код органа, а не поток: без
    обёртки contextvar в новом потоке пуст, страж не активен — ренегат выносит
    нарушение за границу полномочий молча (слепая зона волны №7). На Python 3.14+
    появилось родное audit-событие `threading.start` — обёртка может быть снята
    (SPEC-0002 п.8 v0.6.0). Граница действия: поток, рождённый вне стража, и поток,
    переиспользованный чужим контекстом, стража не имеют — это граница, не дыра.
    """
    global _thread_wrap_installed
    original_start = threading.Thread.start

    def guarded_start(self: threading.Thread) -> None:
        guard = _ACTIVE.get()
        if guard is not None and getattr(self, "_commons_original_run", None) is None:
            original_run = self.run

            def inherited_run() -> None:
                token = _ACTIVE.set(guard)
                try:
                    original_run()
                finally:
                    _ACTIVE.reset(token)

            self._commons_original_run = original_run  # маркер: не оборачиваем дважды
            self.run = inherited_run  # атрибут экземпляра затеняет метод класса
        original_start(self)

    threading.Thread.start = guarded_start  # type: ignore[method-assign]
    _thread_wrap_installed = True


def _repo_root() -> str:
    """Корень дома (для PYTHONPATH детёныша: sitecustomize ищем там)."""
    global _repo_root_cached
    if _repo_root_cached is None:
        _repo_root_cached = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return _repo_root_cached


def _install_popen_inheritance() -> None:
    """Детёныш получает конверт полномочий (v0.7.0): обёртка Popen.__init__ — один раз на
    процесс, идемпотентно. execve роняет audit hook — внутри чужого процесса стража нет;
    питоновский детёныш загружает страж на старте по конверту COMMONS_AUTHORITY
    (sitecustomize), чужой бинарник конверта не читает — честная граница (SPEC-0002 п.8).
    """
    global _popen_wrap_installed
    original_init = subprocess.Popen.__init__

    def guarded_init(self: subprocess.Popen, args: Any, *pos_args: Any, **kwargs: Any) -> None:
        guard = _ACTIVE.get()
        if guard is not None:
            args, kwargs = _popen_scope(guard, args, kwargs)
        original_init(self, args, *pos_args, **kwargs)

    subprocess.Popen.__init__ = guarded_init  # type: ignore[method-assign]
    _popen_wrap_installed = True


def _popen_scope(guard: Guard, args: tuple, kwargs: dict) -> tuple[tuple, dict]:
    """Рождение детёныша: скоуп (programs/max_children/shell) до создания процесса +
    конверт полномочий в окружении — наследование и при ярлыке spawn (v0.7.0)."""
    process = guard.authority.get("process", "none")
    if isinstance(process, dict):
        if kwargs.get("shell"):
            raise AuthorityViolation(_text(guard, "subprocess.Popen", "process: скоуп", "shell: True со скоупом process — argv не разбираем (fail-closed)"))
        prog_path = kwargs.get("executable") or (args[0] if args else None)
        program = os.path.basename(os.fsdecode(prog_path)) if isinstance(prog_path, (str, bytes)) and prog_path else None
        declared = {os.path.basename(os.fsdecode(p)) for p in process["programs"]}
        if program is None or program not in declared:
            raise AuthorityViolation(_text(guard, "subprocess.Popen", f"process: programs {process['programs']}", f"программа детёныша вне заявленных программ: {prog_path!r}"))
        limit = process.get("max_children")
        if limit is not None:
            spawned = getattr(_local, "spawned", 0)
            if spawned >= limit:
                raise AuthorityViolation(_text(guard, "subprocess.Popen", f"process: max_children {limit}", f"лимит детёнышей исчерпан (рождено {spawned})"))
            _local.spawned = spawned + 1
        if process.get("sandbox"):
            # Ядерная песочница детёныша (v0.8.0, п.11): preexec_fn ставит seccomp-BPF до execve —
            # фильтр наследуется execve и всеми потомками независимо от языка.
            if "preexec_fn" in kwargs:
                raise AuthorityViolation(_text(guard, "subprocess.Popen", "process: sandbox", "preexec_fn занят стражем: песочница ставится в этот слот (v0.8.0)"))
            kwargs["preexec_fn"] = apply_child_sandbox
    env = kwargs.get("env")
    child_env = dict(env) if isinstance(env, dict) else os.environ.copy()  # окружение вызывающего не мутируем
    child_env[ACTIVE_ENV] = json.dumps({"organ": guard.organ, "authority": guard.authority}, ensure_ascii=False)
    root = _repo_root()
    parts = [p for p in child_env.get("PYTHONPATH", "").split(os.pathsep) if p]
    if root not in parts:
        child_env["PYTHONPATH"] = os.pathsep.join([root, *parts])
    kwargs["env"] = child_env
    return args, kwargs


# --- ядерная песочница детёнышей (v0.8.0, п.11) ------------------------------------

_SANDBOX_PROG: Any = None  # собранный фильтр (кэш на процесс)


def _sandbox_bpf() -> Any:
    """seccomp-BPF: socket(AF_INET/AF_INET6) → EPERM, остальное — ALLOW, чужая архитектура —
    EPERM (fail-closed). Прыжки выверены живой пробой (inet рвётся, unix жив). Только x86_64:
    на другом ядре/архитектуре фильтр не соберётся — детёныш не живёт (fail-closed, exit 89)."""
    global _SANDBOX_PROG
    if _SANDBOX_PROG is None:
        import ctypes
        import struct

        if sys.platform != "linux" or os.uname().machine != "x86_64":
            raise RuntimeError("seccomp-песочница собрана только для linux/x86_64")

        class _SockFilter(ctypes.Structure):
            _fields_ = [("code", ctypes.c_uint16), ("jt", ctypes.c_uint8),
                        ("jf", ctypes.c_uint8), ("k", ctypes.c_uint32)]

        class _SockFprog(ctypes.Structure):
            _fields_ = [("len", ctypes.c_uint16), ("filter", ctypes.POINTER(_SockFilter))]

        LD_ABS, JEQ, RET = 0x20, 0x15, 0x06
        ALLOW, EPERM = 0x7FFF0000, 0x00050000 | 1
        prog = [
            _SockFilter(LD_ABS, 0, 0, 4),        # 0: arch
            _SockFilter(JEQ, 0, 7, 0xC000003E),  # 1: ≠x86_64 → idx9 EPERM (fail-closed)
            _SockFilter(LD_ABS, 0, 0, 0),        # 2: nr
            _SockFilter(JEQ, 0, 4, 41),          # 3: ≠socket → idx8 ALLOW
            _SockFilter(LD_ABS, 0, 0, 16),       # 4: args[0] = domain
            _SockFilter(JEQ, 1, 0, 2),           # 5: =AF_INET → idx7 EPERM
            _SockFilter(JEQ, 1, 1, 10),          # 6: =AF_INET6 → idx7 EPERM; иначе → idx8 ALLOW
            _SockFilter(RET, 0, 0, EPERM),       # 7
            _SockFilter(RET, 0, 0, ALLOW),       # 8
            _SockFilter(RET, 0, 0, EPERM),       # 9
        ]
        _SANDBOX_PROG = (_SockFprog(len(prog), (_SockFilter * len(prog))(*prog)), struct, ctypes)
    return _SANDBOX_PROG[0]


def apply_child_sandbox() -> None:
    """Ядерная песочница детёныша (v0.8.0, п.11): preexec_fn детёныша — до execve ставит
    seccomp-BPF (socket(AF_INET/AF_INET6) → EPERM). NO_NEW_PRIVS не даёт фильтр снять,
    фильтры только стекаются, наследуются execve и всеми потомками независимо от языка.
    Песочница не поставилась — детёныш не живёт (os._exit(89), fail-closed)."""
    try:
        import ctypes

        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
            os._exit(89)
        prog = _sandbox_bpf()
        if libc.prctl(22, 2, ctypes.byref(prog), 0, 0) != 0:  # PR_SET_SECCOMP, SECCOMP_MODE_FILTER
            os._exit(89)
    except BaseException:  # noqa: BLE001 — детёныш без песочницы не живёт
        os._exit(89)


def boot_child(raw: str) -> None:
    """Загрузка стража в детёныше (v0.7.0): конверт COMMONS_AUTHORITY -> пожизненный страж
    процесса (contextvar держится до смерти). Битый конверт — AuthorityConfigError:
    sitecustomize роняет детёныш до первого оператора (fail-closed)."""
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or not isinstance(data.get("authority"), dict):
            raise ValueError("конверт обязан быть dict с authority")
        authority = normalize(data["authority"], organ=str(data.get("organ") or "-"))
    except Exception as exc:
        raise AuthorityConfigError(f"детёныш: {ACTIVE_ENV} не разобран ({type(exc).__name__}: {exc})") from None
    _ACTIVE.set(Guard(str(data.get("organ") or "-"), authority))
    _install_hook()


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
            _check_mutation(guard, event, args)
        elif event.startswith("socket."):
            _check_socket(guard, event, args)
        elif not _spawn_allowed(guard.authority.get("process", "none")):
            raise AuthorityViolation(_text(guard, "subprocess.Popen", f"process: {guard.authority.get('process', 'none')}", "создание процессов запрещено"))
    except AuthorityViolation:
        raise
    except Exception as exc:  # кривые args: событие охраняемое — fail-closed (SPEC-0002 G1)
        raise AuthorityViolation(_text(guard, event, "fail-closed", f"событие не разобрано: {type(exc).__name__}: {exc}")) from None


def _text(guard: Guard, event: str, rule: str, detail: str) -> str:
    return f"орган {guard.organ!r}: {event} {detail} — нарушено заявленное правило ({rule})"


def _spawn_allowed(process: Any) -> bool:
    """spawn разрешён ярлыком или скоупом (детальный скоуп проверяет обёртка Popen, v0.7.0)."""
    return process == "spawn" or (isinstance(process, dict) and process.get("mode") == "spawn")


def _pycache_hint(path: Any) -> str:
    """Предписание к записи байткода (v0.6.0): диагностика, не послабление — запись прервана."""
    if not isinstance(path, (str, bytes)) or not path:
        return ""
    try:
        clean = os.path.abspath(os.fsdecode(path))
    except (OSError, ValueError):
        return ""
    if "__pycache__" in clean.split(os.sep) or clean.endswith(".pyc"):
        return f" ({_PYCACHE_PRESCRIPTION})"
    return ""


def _check_open(guard: Guard, args: tuple) -> None:
    path = args[0] if args else None
    mode = args[1] if len(args) > 1 else None
    flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
    fs = guard.authority.get("fs", "none")
    writing = (isinstance(mode, str) and _WRITE_MODE_CHARS.intersection(mode)) or bool(flags & _WRITE_FLAGS)
    if writing:
        if isinstance(fs, dict):
            if fs.get("mode") != "read-write" or not _inside_roots(fs.get("paths") or [], path):
                raise AuthorityViolation(_text(guard, "open", f"fs: {fs.get('mode')} скоуп {fs.get('paths')}", f"запись вне заявленных корней: {path!r} {_pycache_hint(path)}".rstrip()))
        elif fs != "read-write":
            raise AuthorityViolation(_text(guard, "open", f"fs: {fs}", f"запись запрещена: {path!r} (режим {mode!r}){_pycache_hint(path)}"))
    elif not _under_python_runtime(path):
        if isinstance(fs, dict):
            if not _inside_roots(fs.get("paths") or [], path):
                raise AuthorityViolation(_text(guard, "open", f"fs: {fs.get('mode')} скоуп {fs.get('paths')}", f"чтение вне заявленных корней: {path!r}"))
        elif fs == "none":
            raise AuthorityViolation(_text(guard, "open", "fs: none", f"чтение запрещено (кроме рантайма Python): {path!r}"))


def _check_mutation(guard: Guard, event: str, args: tuple) -> None:
    """Мутации ФС (remove/rename/mkdir/rmdir/chmod/chown): при скоупе — только внутри корней (rename — оба конца)."""
    fs = guard.authority.get("fs", "none")
    if isinstance(fs, dict):
        if fs.get("mode") != "read-write":
            raise AuthorityViolation(_text(guard, event, f"fs: {fs.get('mode')} скоуп", "мутация файловой системы запрещена"))
        targets = list(args[:2]) if event == "os.rename" else args[:1]
        for target in targets:
            if not _inside_roots(fs.get("paths") or [], target):
                raise AuthorityViolation(_text(guard, event, f"fs: {fs.get('mode')} скоуп {fs.get('paths')}", f"цель вне заявленных корней: {target!r}"))
        return
    if fs != "read-write":
        raise AuthorityViolation(_text(guard, event, f"fs: {fs}", "мутация файловой системы запрещена"))


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


def _inside_roots(roots: list[str], path: Any) -> bool:
    """Скоуп (v0.5.0): цель внутри заявленного корня; сравнение по realpath — симлинк-побег закрыт.
    Непарсабельная цель — вне (fail-closed)."""
    if not isinstance(path, (str, bytes)) or not path:
        return False
    try:
        clean = os.path.realpath(os.path.abspath(os.fsdecode(path)))
    except (OSError, ValueError):
        return False
    for root in roots:
        try:
            base = os.path.realpath(os.path.abspath(os.fsdecode(root)))
        except (OSError, ValueError):
            continue
        if clean == base or clean.startswith(base + os.sep):
            return True
    return False


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
    ports = net.get("ports") if isinstance(net, dict) else None
    if ports and event in ("socket.connect", "socket.bind"):  # getaddrinfo порта не несёт (v0.5.0)
        port = _socket_port(args)
        if port is None or port not in ports:
            raise AuthorityViolation(_text(guard, event, f"network: ports {ports}", f"порт вне полномочий: {port!r}"))


def _socket_host(event: str, args: tuple) -> Any:
    """Хост события: connect/bind — args[1] (адрес), getaddrinfo — args[0]; None = не разобран."""
    if event == "socket.getaddrinfo":
        return args[0] if args else None
    if len(args) > 1 and isinstance(args[1], tuple) and args[1]:
        return args[1][0]
    if len(args) > 1 and isinstance(args[1], (str, bytes)):
        return args[1]  # unix-сокет: путь
    return None


def _socket_port(args: tuple) -> int | None:
    """Порт события connect/bind — второй элемент адресного кортежа; None = не разобран."""
    if len(args) > 1 and isinstance(args[1], tuple) and len(args[1]) > 1 and isinstance(args[1][1], int):
        return args[1][1]
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
