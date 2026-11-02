"""Живой прогон волны №13 такт 2: защита в глубину и граница R1 (SPEC-0002 v0.9.0, п.11).

Слой поверх их ядерной песочницы (0.31.0, п.11) — один трек A, один трек B (донорская
книга, donors.md), одно другое не исключает (директива Человека «ТЫ ПОЛИМАТ=МУЛЬТИАГЕНТ»).
Прогон печатает факты, не предсказания. Сцены:
1. curl (чужой бинарник) под песочницей — свидетель 0 (их сцена была sh -c; тут чужой бинарь);
2. ctypes raw-syscall (находка C13) — socket ронят ядром ДО кода детёныша, audit hook слеп;
3. UDP sendto (находка U1) — дейтаграмма не уходит, socket(AF_INET, DGRAM) → EPERM;
4. безсетевая программа жива: curl --version под песочницей;
5. unix-сокет жив: socket(AF_UNIX) — их граница подтверждена;
6. без sandbox inet жив (граница действия): детёныш соединяется, свидетель 1;
7. **факт R1**: детёныш соединяется по УНАСЛЕДОВАННОМУ дескриптору (создан до стража,
   передан pass_fds) raw-connect'ом — и их фильтр, и страж слепы, свидетель 1;
   приёмка-предписание в сюите покраснеет при закрытии R1;
8. кровь волны: цепочка prev_id цела — verify: 0 гэпов, chained=true.

Кровь волны пишется тем же журналом: runs/2026-11-03-wave13-seccomp/blood.jsonl.
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

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import make  # noqa: E402
from blood.journal import Journal, verify  # noqa: E402
from synapse.authority import enforce  # noqa: E402

RUN_DIR = Path(__file__).resolve().parent
BLOOD_PATH = RUN_DIR / "blood.jsonl"

GREEN: list[str] = []
RED: list[str] = []

BLOOD_JOURNAL = Journal()
BLOOD_JOURNAL.attach(BLOOD_PATH)
TRACE = "wave13-takt2-seccomp"

PYTHON = Path(sys.executable).name
SCOPE_SANDBOX = {
    "fs": "read-only",
    "network": "none",
    "process": {"mode": "spawn", "programs": [PYTHON, "curl", "sh"], "sandbox": {"network": "none"}},
}


def verdict(ok: bool, name: str, detail: str) -> None:
    (GREEN if ok else RED).append(f"{name}: {detail}")
    kind = "reflect" if ok else "error"
    BLOOD_JOURNAL.append(
        make(kind, "wave13", "self", TRACE, {"scene": name, "detail": detail, "verdict": "green" if ok else "red"})
    )
    print(f"[ЗЕЛЁНО] {name}: {detail}" if ok else f"[КРАСНО] {name}: {detail}")


def fact(name: str, detail: str) -> None:
    BLOOD_JOURNAL.append(make("observe", "wave13", "self", TRACE, {"scene": name, "detail": detail}))
    print(f"[ФАКТ] {name}: {detail}")


def scene_plan(name: str, index: int) -> None:
    BLOOD_JOURNAL.append(make("plan", "wave13", "self", TRACE, {"scene": name, "index": index}))


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


# --- сцена 1: чужой бинарник под песочницей ------------------------------------------

def scene_foreign_binary() -> None:
    scene_plan("foreign-binary", 1)
    with witness("tcp") as (port, hits):
        with enforce(SCOPE_SANDBOX, organ="w13b-curl"):
            proc = subprocess.run(
                ["curl", "--max-time", "2", "-s", f"http://127.0.0.1:{port}/"],
                capture_output=True, text=True, timeout=20,
            )
    verdict(
        not hits and proc.returncode != 0,
        "1: curl под песочницей не соединяется",
        f"свидетель видел {len(hits)} (в волне №12 был 1), returncode={proc.returncode} — "
        "фильтр пережил execve, чужой бинарь закрыт ядром",
    )


# --- сцена 2: ctypes raw-syscall (находка C13) ----------------------------------------

def scene_ctypes_bypass() -> None:
    scene_plan("ctypes-bypass", 2)
    code = (
        "import ctypes, socket, struct\n"
        "libc = ctypes.CDLL('libc.so.6', use_errno=True)\n"
        "port = int(__import__('os').environ['W13_PORT'])\n"
        "sa = struct.pack('HH4s8s', 2, socket.htons(port), bytes([127, 0, 0, 1]), b'\\x00' * 8)\n"
        "fd = libc.socket(2, 1, 0)\n"
        "if fd < 0:\n"
        "    print('SOCKET-EPERM')\n"
        "else:\n"
        "    print('LEAKED' if libc.connect(fd, sa, len(sa)) == 0 else 'CONNECT-EPERM')\n"
    )
    with witness("tcp") as (port, hits):
        with enforce(SCOPE_SANDBOX, organ="w13b-ctypes"):
            env = dict(os.environ, W13_PORT=str(port))
            proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=20, env=env)
    verdict(
        "LEAKED" not in proc.stdout and not hits,
        "2: ctypes raw-syscall ронят (находка C13)",
        f"audit hook'у нечего перехватывать (libc.socket — вне грамматики), ядро роняло socket() до кода "
        f"детёныша: stdout={proc.stdout.strip()!r}, свидетель видел {len(hits)} — защита в глубину",
    )


# --- сцена 3: UDP sendto (находка U1) ---------------------------------------------------

def scene_udp_leak() -> None:
    scene_plan("udp-leak", 3)
    code = (
        "import socket\n"
        "port = int(__import__('os').environ['W13_PORT'])\n"
        "s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)\n"
        "s.sendto(b'leak', ('127.0.0.1', port))\n"
        "print('UDP-LEAKED')\n"
    )
    with witness("udp") as (port, hits):
        with enforce(SCOPE_SANDBOX, organ="w13b-udp"):
            env = dict(os.environ, W13_PORT=str(port))
            proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=20, env=env)
    verdict(
        "UDP-LEAKED" not in proc.stdout and not hits,
        "3: UDP sendto ронят (находка U1)",
        f"sendto — не audit-событие (страж слеп), ядро роняло socket(AF_INET, DGRAM) как inet: "
        f"stdout={proc.stdout.strip()!r}, свидетель видел {len(hits)} дейтаграмм, returncode={proc.returncode}",
    )


# --- сцена 4: безсетевая программа жива ---------------------------------------------------

def scene_network_free_program() -> None:
    scene_plan("network-free-program", 4)
    with enforce(SCOPE_SANDBOX, organ="w13b-version"):
        proc = subprocess.run(["curl", "--version"], capture_output=True, text=True, timeout=20)
    verdict(
        proc.returncode == 0 and "curl" in proc.stdout,
        "4: безсетевая программа жива под песочницей",
        f"curl --version: returncode={proc.returncode} — граница не рвёт детёнышей, которым сеть не нужна",
    )


# --- сцена 5: unix-сокет жив ---------------------------------------------------------------

def scene_unix_alive() -> None:
    scene_plan("unix-alive", 5)
    code = "import socket; socket.socket(1, 1).close(); print('UNIX-LIVE')"
    with enforce(SCOPE_SANDBOX, organ="w13b-unix"):
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=20)
    verdict(
        "UNIX-LIVE" in proc.stdout,
        "5: unix-сокет жив",
        f"socket(AF_UNIX) жив под песочницей ({proc.stdout.strip()!r}) — локальный обмен не сеть, граница названа",
    )


# --- сцена 6: без sandbox — граница действия -------------------------------------------------

def scene_no_sandbox_boundary() -> None:
    scene_plan("no-sandbox-boundary", 6)
    # (а) без sandbox ядро не роняет syscall: inet-socket создаётся живьём (их приёмка, их PROBE_INET)
    probe = "import socket; socket.socket(2, 1).close(); print('INET-SOCKET-LIVE')"
    scope = {"fs": "read-only", "network": "none", "process": "spawn"}
    with enforce(scope, organ="w13b-nosandbox-syscall"):
        p_syscall = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=20)
    # (б) соединение питоновский детёныш под конвертом не делает — ронято стражем (волна №12), свидетель 0
    with witness("tcp") as (port, hits):
        connect_code = (
            f"import socket; s=socket.create_connection(('127.0.0.1', {port}), timeout=3); "
            "s.sendall(b'ok'); s.close(); print('LOCAL-OK')"
        )
        with enforce(scope, organ="w13b-nosandbox-connect"):
            p_connect = subprocess.run([sys.executable, "-c", connect_code], capture_output=True, text=True, timeout=20)
    verdict(
        "INET-SOCKET-LIVE" in p_syscall.stdout and "LOCAL-OK" not in p_connect.stdout
        and "AuthorityViolation" in p_connect.stderr and not hits,
        "6: без sandbox — прежняя граница честно на месте",
        f"ядро syscall не роняет ({p_syscall.stdout.strip()!r}), соединение роняно стражем в детёныше "
        f"(returncode={p_connect.returncode}, AuthorityViolation в stderr), свидетель видел {len(hits)} — "
        "граница действия их волны: без sandbox ядро не участвует, страж продолжает работать (волна №12)",
    )


# --- сцена 7: факт R1 — унаследованный дескриптор ----------------------------------------------

def scene_inherited_fd() -> None:
    scene_plan("inherited-fd", 7)
    with witness("tcp") as (port, hits):
        leak_fd = socket.socket()  # создан ДО стража: родитель под network: none его не открывал
        fd = leak_fd.fileno()
        code = (
            "import ctypes, os, socket, struct\n"
            "port = int(__import__('os').environ['W13_PORT'])\n"
            "sa = struct.pack('HH4s8s', 2, socket.htons(port), bytes([127, 0, 0, 1]), b'\\x00' * 8)\n"
            "libc = ctypes.CDLL('libc.so.6', use_errno=True)\n"
            "rc = libc.connect(int(os.environ['LEAK_FD']), sa, len(sa))\n"
            "print('FD-LEAKED' if rc == 0 else 'FD-BLOCKED')\n"
        )
        with enforce(SCOPE_SANDBOX, organ="w13b-inherited"):
            env = dict(os.environ, W13_PORT=str(port), LEAK_FD=str(fd))
            proc = subprocess.run(
                [sys.executable, "-c", code], capture_output=True, text=True, timeout=20,
                pass_fds=(fd,), env=env,
            )
        leak_fd.close()
    fact(
        "7: граница R1 — унаследованный дескриптор",
        f"детёныш под песочницей соединился raw-connect'ом по переданному fd: stdout={proc.stdout.strip()!r}, "
        f"свидетель видел {len(hits)} — их фильтр роняет socket(), но не connect по унаследованному дескриптору; "
        "страж слеп к raw-syscall; в крови обычный act. Приёмка-предписание в сюите покраснеет при закрытии "
        "R1 (гигиена pass_fds под стражем или deny connect — с честным названием unix-границы)",
    )


# --- сцена 8: кровь волны ------------------------------------------------------------------------

def scene_blood() -> None:
    scene_plan("wave-blood", 8)
    BLOOD_JOURNAL.append(
        make("halt" if RED else "shutdown", "wave13", "self", TRACE, {"verdicts": len(GREEN), "red": len(RED)})
    )
    BLOOD_JOURNAL.close()
    report = verify(BLOOD_PATH)
    verdict(
        report["gaps"] == [] and report["chained"],
        "8: кровь волны цела",
        f"{report['events']} конвертов, гэпов {len(report['gaps'])}, chained={report['chained']}",
    )
    print(f"\nИТОГ: {len(GREEN)} зелёных / {len(RED)} красных")
    if RED:
        for line in RED:
            print(f"  КРАСНО: {line}")
        sys.exit(1)


def main() -> None:
    scene_foreign_binary()
    scene_ctypes_bypass()
    scene_udp_leak()
    scene_network_free_program()
    scene_unix_alive()
    scene_no_sandbox_boundary()
    scene_inherited_fd()
    scene_blood()


if __name__ == "__main__":
    main()
