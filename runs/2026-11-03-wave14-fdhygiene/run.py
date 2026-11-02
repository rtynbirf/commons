"""Живой прогон волны №14: гигиена дескрипторов и рождения мимо обёртки (SPEC-0002 v0.10.0).

Закрытие границы R1 (названа волной №13) + переворот находки R2 (живая разведка волны №14).
Прогон печатает факты, не предсказания. Сцены:
1. R1 закрыта: сокет-fd в pass_fds при network: none — рождение прервано ДО execve
   (в волне №13 соединение проходило, свидетель видел 1);
2. network: any — capability заявлена: raw-connect по fd жив, свидетель 1;
3. пайп в pass_fds — детёныш жив: гигиена не рвёт не-сетевые дескрипторы;
4. stdout=сокет при network: none — рождение прервано (тот же канал, stdio);
5. close_fds=False при живых сокетах — рождение прервано (наследует весь стол);
6. детёныш с просочившимся fd (ручной конверт, мимо обёртки) — сам-скан, exit 90;
7. контроль: детёныш с конвертом без чужих сокетов — жив;
8. R2: os.posix_spawn при network: none — прерван (конверт не передаётся);
9. R2: os.system — прерван всегда (строка shell не разбираем);
10. контроль: обычное рождение под стражем живо — гигиена не рвёт быт;
11. кровь волны: цепочка prev_id цела — verify: 0 гэпов, chained=true.

Кровь волны пишется тем же журналом: runs/2026-11-03-wave14-fdhygiene/blood.jsonl.
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

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import make  # noqa: E402
from blood.journal import Journal, verify  # noqa: E402
from synapse.authority import AuthorityViolation, enforce  # noqa: E402

RUN_DIR = Path(__file__).resolve().parent
BLOOD_PATH = RUN_DIR / "blood.jsonl"

GREEN: list[str] = []
RED: list[str] = []

BLOOD_JOURNAL = Journal()
BLOOD_JOURNAL.attach(BLOOD_PATH)
TRACE = "wave14-fdhygiene"

PYTHON = Path(sys.executable).name
SCOPE_SPAWN = {
    "fs": "read-only",
    "network": "none",
    "process": {"mode": "spawn", "programs": [PYTHON, "curl", "sh"]},
}
SCOPE_SPAWN_ANY = {
    "fs": "read-only",
    "network": "any",
    "process": {"mode": "spawn", "programs": [PYTHON]},
}


def verdict(ok: bool, name: str, detail: str) -> None:
    (GREEN if ok else RED).append(f"{name}: {detail}")
    kind = "reflect" if ok else "error"
    BLOOD_JOURNAL.append(
        make(kind, "wave14", "self", TRACE, {"scene": name, "detail": detail, "verdict": "green" if ok else "red"})
    )
    print(f"[ЗЕЛЁНО] {name}: {detail}" if ok else f"[КРАСНО] {name}: {detail}")


def fact(name: str, detail: str) -> None:
    BLOOD_JOURNAL.append(make("observe", "wave14", "self", TRACE, {"scene": name, "detail": detail}))
    print(f"[ФАКТ] {name}: {detail}")


def scene_plan(name: str, index: int) -> None:
    BLOOD_JOURNAL.append(make("plan", "wave14", "self", TRACE, {"scene": name, "index": index}))


@contextmanager
def witness() -> Iterator[tuple[int, list[str]]]:
    """Живой свидетель: слушает loopback, считает каждое настоящее соединение."""
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


def raw_connect_code(port: int) -> str:
    return (
        "import ctypes, os, socket, struct\n"
        f"sa = struct.pack('HH4s8s', 2, socket.htons({port}), bytes([127, 0, 0, 1]), b'\\x00' * 8)\n"
        "libc = ctypes.CDLL('libc.so.6', use_errno=True)\n"
        "rc = libc.connect(int(os.environ['LEAK_FD']), sa, len(sa))\n"
        "print('FD-LEAKED' if rc == 0 else 'FD-BLOCKED')\n"
    )


# --- сцена 1: R1 закрыта -------------------------------------------------------------

def scene_r1_closed() -> None:
    scene_plan("r1-closed", 1)
    violation = ""
    with witness() as (port, hits):
        leak_fd = socket.socket()  # создан ДО стража — как в красном прогоне волны №13
        fd = leak_fd.fileno()
        born = False
        try:
            with enforce(SCOPE_SPAWN, organ="w14-r1"):
                subprocess.run(
                    [sys.executable, "-c", raw_connect_code(port)], capture_output=True, text=True,
                    timeout=20, pass_fds=(fd,), env=dict(os.environ, LEAK_FD=str(fd)),
                )
            born = True  # рождение не прервано — R1 жива
        except AuthorityViolation as exc:
            violation = str(exc)
        finally:
            leak_fd.close()
    verdict(
        not born and hits == [],
        "1: R1 закрыта — сокет-fd в pass_fds прерван",
        f"рождение прервано ДО execve (свидетель {len(hits)}); текст: {violation[:170]}",
    )


# --- сцена 2: network any — capability заявлена ---------------------------------------

def scene_network_any_alive() -> None:
    scene_plan("any-alive", 2)
    with witness() as (port, hits):
        leak_fd = socket.socket()
        fd = leak_fd.fileno()
        try:
            with enforce(SCOPE_SPAWN_ANY, organ="w14-any"):
                proc = subprocess.run(
                    [sys.executable, "-c", raw_connect_code(port)], capture_output=True, text=True,
                    timeout=20, pass_fds=(fd,), env=dict(os.environ, LEAK_FD=str(fd)),
                )
        finally:
            leak_fd.close()
    verdict(
        "FD-LEAKED" in proc.stdout and len(hits) == 1,
        "2: network any — fd жив (capability заявлена)",
        f"stdout={proc.stdout.strip()!r}, свидетель {len(hits)} — гигиена не рвёт заявленное",
    )


# --- сцена 3: пайп жив ----------------------------------------------------------------

def scene_pipe_alive() -> None:
    scene_plan("pipe-alive", 3)
    r, w = os.pipe()
    try:
        with enforce(SCOPE_SPAWN, organ="w14-pipe"):
            proc = subprocess.run(
                [sys.executable, "-c", "print('PIPED')"], capture_output=True, text=True,
                timeout=20, pass_fds=(w,),
            )
    finally:
        os.close(r)
        os.close(w)
    verdict(
        proc.returncode == 0 and "PIPED" in proc.stdout,
        "3: пайп в pass_fds жив",
        f"rc={proc.returncode} — гигиена рвёт только сокеты",
    )


# --- сцена 4: stdio на сокет прерван ---------------------------------------------------

def scene_stdio_socket() -> None:
    scene_plan("stdio-socket", 4)
    leak_fd = socket.socket()
    fd = leak_fd.fileno()
    born = False
    violation = ""
    try:
        with enforce(SCOPE_SPAWN, organ="w14-stdio"):
            subprocess.run([sys.executable, "-c", "print('BORN')"], stdout=fd, timeout=20)
        born = True
    except AuthorityViolation as exc:
        violation = str(exc)
    finally:
        leak_fd.close()
    verdict(
        not born,
        "4: stdout=сокет при network none прерван",
        f"рождение прервано: {violation[:170]}",
    )


# --- сцена 5: close_fds=False с сокетами прерван ----------------------------------------

def scene_close_fds_false() -> None:
    scene_plan("close-fds-false", 5)
    extra = socket.socket()
    born = False
    violation = ""
    try:
        with enforce(SCOPE_SPAWN, organ="w14-closefds"):
            subprocess.run(
                [sys.executable, "-c", "print('BORN')"], capture_output=True, text=True,
                timeout=20, close_fds=False,
            )
        born = True
    except AuthorityViolation as exc:
        violation = str(exc)
    finally:
        extra.close()
    verdict(
        not born,
        "5: close_fds=False с сокетами прерван",
        f"рождение прервано: {violation[:170]}",
    )


# --- сцена 6: детёныш с просочившимся fd не живёт (сам-скан, exit 90) --------------------

def scene_child_self_scan() -> None:
    scene_plan("child-self-scan", 6)
    leak_fd = socket.socket()
    fd = leak_fd.fileno()
    envelope = json.dumps({"organ": "leaked-child", "authority": SCOPE_SPAWN})
    env = dict(os.environ, COMMONS_AUTHORITY=envelope, PYTHONPATH=str(REPO_ROOT))
    try:
        proc = subprocess.run(
            [sys.executable, "-c", "print('CHILD_ALIVE')"], capture_output=True, text=True,
            timeout=20, pass_fds=(fd,), env=env,
        )
    finally:
        leak_fd.close()
    verdict(
        proc.returncode == 90 and "CHILD_ALIVE" not in proc.stdout,
        "6: детёныш с просочившимся fd не живёт (exit 90)",
        f"rc={proc.returncode}, stderr={proc.stderr.strip()[-120:]!r} — сам-скан до первого оператора",
    )


# --- сцена 7: контроль — детёныш без чужих сокетов жив -----------------------------------

def scene_child_clean_alive() -> None:
    scene_plan("child-clean", 7)
    envelope = json.dumps({"organ": "clean-child", "authority": SCOPE_SPAWN})
    env = dict(os.environ, COMMONS_AUTHORITY=envelope, PYTHONPATH=str(REPO_ROOT))
    proc = subprocess.run(
        [sys.executable, "-c", "print('CHILD_ALIVE')"], capture_output=True, text=True,
        timeout=20, env=env,
    )
    verdict(
        proc.returncode == 0 and "CHILD_ALIVE" in proc.stdout,
        "7: контроль — детёныш без чужих сокетов жив",
        f"rc={proc.returncode} — сам-скан не рвёт обычных детёнышей",
    )


# --- сцена 8: R2 — os.posix_spawn --------------------------------------------------------

def scene_posix_spawn() -> None:
    scene_plan("posix-spawn", 8)
    born = False
    violation = ""
    try:
        with enforce(SCOPE_SPAWN, organ="w14-posix"):
            os.posix_spawn("/bin/true", ["/bin/true"], {})
        born = True
    except AuthorityViolation as exc:
        violation = str(exc)
    verdict(
        not born,
        "8: R2 — os.posix_spawn при network none прерван",
        f"рождение мимо обёртки прервано: {violation[:170]}",
    )


# --- сцена 9: R2 — os.system --------------------------------------------------------------

def scene_os_system() -> None:
    scene_plan("os-system", 9)
    results: list[str] = []
    for label, scope in (
        ("process: none", {"fs": "read-only", "network": "any", "process": "none"}),
        ("скоуп", SCOPE_SPAWN_ANY),
    ):
        born = False
        try:
            with enforce(scope, organ="w14-system"):
                os.system("true")
            born = True
        except AuthorityViolation as exc:
            results.append(f"{label}: прерван ({str(exc)[-90:]})")
        if born:
            results.append(f"{label}: РОДИЛСЯ")
    verdict(
        all("РОДИЛСЯ" not in r for r in results) and len(results) == 2,
        "9: R2 — os.system прерван всегда (shell-строка не разбираем)",
        "; ".join(results),
    )


# --- сцена 10: контроль — обычное рождение живо -------------------------------------------

def scene_plain_spawn_alive() -> None:
    scene_plan("plain-spawn", 10)
    with enforce(SCOPE_SPAWN, organ="w14-plain"):
        proc = subprocess.run([sys.executable, "-c", "print('FREE')"], capture_output=True, text=True, timeout=20)
    verdict(
        proc.returncode == 0 and "FREE" in proc.stdout,
        "10: контроль — обычное рождение живо",
        f"rc={proc.returncode} — гигиена не рвёт быт организма",
    )


# --- сцена 11: кровь волны ------------------------------------------------------------------

def scene_blood() -> None:
    scene_plan("wave-blood", 11)
    BLOOD_JOURNAL.append(
        make("halt" if RED else "shutdown", "wave14", "self", TRACE, {"verdicts": len(GREEN), "red": len(RED)})
    )
    BLOOD_JOURNAL.close()
    report = verify(BLOOD_PATH)
    verdict(
        report["gaps"] == [] and report["chained"],
        "11: кровь волны цела",
        f"{report['events']} конвертов, гэпов {len(report['gaps'])}, chained={report['chained']}",
    )
    print(f"\nИТОГ: {len(GREEN)} зелёных / {len(RED)} красных")
    if RED:
        for line in RED:
            print(f"  КРАСНО: {line}")
        sys.exit(1)


def main() -> None:
    scene_r1_closed()
    scene_network_any_alive()
    scene_pipe_alive()
    scene_stdio_socket()
    scene_close_fds_false()
    scene_child_self_scan()
    scene_child_clean_alive()
    scene_posix_spawn()
    scene_os_system()
    scene_plain_spawn_alive()
    scene_blood()


if __name__ == "__main__":
    main()
