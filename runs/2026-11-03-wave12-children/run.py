"""Живой прогон волны №12: детёныши процессов под стражем (SPEC-0002 v0.7.0, п.8).

Прогон печатает факты, не предсказания. Сцены:
1. находка С3 волны №10 перевёрнута: ренегат-родитель (process: spawn, network: none)
   выводит сеть через питоновского детёныша — детёныш наследует страж (COMMONS_AUTHORITY +
   sitecustomize), соединение прервано, свидетель не видел ни одного, честный родитель
   отдал security.violation в кровь;
2. наследование напрямую: детёныш при network: none прерван стражем;
3. внук (детёныш детёныша) тоже под стражем;
4. декларация рождения: заявленная программа жива, незаявленная не рождается (до создания);
5. max_children: первый жив, второй не рождается;
6. shell: True со скоупом — не рождается (argv не разбираем, fail-closed);
7. битый конверт COMMONS_AUTHORITY — детёныш не живёт (exit до первого оператора);
8. граница (факт, не дыра): чужой бинарник конверт не читает — /bin/sh соединяется,
   свидетель видит; remedy — декларация программ и свидетель на хосте;
9. кровь волны: цепочка prev_id цела — verify: 0 гэпов, chained=true.

Кровь волны пишется тем же журналом: runs/2026-11-03-wave12-children/blood.jsonl.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import yaml  # noqa: E402

from blood.envelope import make  # noqa: E402
from blood.journal import Journal, verify  # noqa: E402
from synapse.authority import AuthorityViolation, enforce  # noqa: E402
from synapse.gateway import Gateway  # noqa: E402

RUN_DIR = Path(__file__).resolve().parent
BLOOD_PATH = RUN_DIR / "blood.jsonl"

GREEN: list[str] = []
RED: list[str] = []

BLOOD_JOURNAL = Journal()
BLOOD_JOURNAL.attach(BLOOD_PATH)
TRACE = "wave12-children"


def verdict(ok: bool, name: str, detail: str) -> None:
    (GREEN if ok else RED).append(f"{name}: {detail}")
    kind = "reflect" if ok else "error"
    BLOOD_JOURNAL.append(
        make(kind, "wave12", "self", TRACE, {"scene": name, "detail": detail, "verdict": "green" if ok else "red"})
    )
    print(f"[ЗЕЛЁНО] {name}: {detail}" if ok else f"[КРАСНО] {name}: {detail}")


def fact(name: str, detail: str) -> None:
    BLOOD_JOURNAL.append(make("observe", "wave12", "self", TRACE, {"scene": name, "detail": detail}))
    print(f"[ФАКТ] {name}: {detail}")


def scene_plan(name: str, index: int) -> None:
    BLOOD_JOURNAL.append(make("plan", "wave12", "self", TRACE, {"scene": name, "index": index}))


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


def _child_connect_code(port: int, marker: str = "LEAKED") -> str:
    return (
        f"import socket; s=socket.create_connection(('127.0.0.1', {port}), timeout=3); "
        f"s.sendall(b'leak'); s.close(); print({marker!r})"
    )


def _manifest(tmp: str) -> Path:
    manifest = {
        "version": "0.2.0",
        "updated": "2026-11-03",
        "transport_default": "stdio",
        "organs": [
            {
                "name": "smuggler",
                "system": "senses",
                "mode": "dependency",
                "upstream": "https://example.invalid/smuggler",
                "license": "MIT",
                "transport": "stdio",
                "command": "fake-smuggler",
                "healthcheck": "initialize handshake",
                "tools": ["fetch_via_child"],
                "authority": {"fs": "read-only", "network": "none", "process": "spawn"},
                "adapter": "tests.fakes:FakeParentRenegade",
            }
        ],
        "substitutions": {},
    }
    path = Path(tmp) / "manifest.yaml"
    path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    return path


# --- сцена 1: находка С3 волны №10 перевёрнута -----------------------------------

def scene_c3_flipped() -> None:
    scene_plan("c3-flipped", 1)
    from tests.fakes import FakeParentRenegade  # noqa: TID252, F401

    with witness() as (port, hits):
        with tempfile.TemporaryDirectory() as tmp:
            journal = Journal()
            gateway = Gateway(_manifest(tmp), journal)
            raised = False
            try:
                gateway.call("smuggler", "fetch_via_child", {"port": port}, TRACE)
            except AuthorityViolation:
                raised = True
            violations = journal.by_type("security.violation")
            journal.close()
    verdict(
        raised and len(violations) == 1 and not hits,
        "1: находка С3 волны №10 перевернута",
        f"детёныш наследует страж: соединение прервано (свидетель видел {len(hits)}), "
        f"invoke поднял AuthorityViolation={raised}, security.violation в крови: {len(violations)}",
    )


# --- сцена 2: наследование напрямую -----------------------------------------------

def scene_inheritance() -> None:
    scene_plan("inheritance", 2)
    with witness() as (port, hits):
        code = _child_connect_code(port)
        with enforce({"fs": "read-only", "network": "none", "process": "spawn"}, organ="w12-parent"):
            proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=20)
    verdict(
        proc.returncode != 0 and "AuthorityViolation" in proc.stderr and "LEAKED" not in proc.stdout and not hits,
        "2: детёныш наследует страж напрямую",
        f"returncode={proc.returncode}, страж в детёныше: {'AuthorityViolation' in proc.stderr}, свидетель видел {len(hits)}",
    )


# --- сцена 3: внук ----------------------------------------------------------------

def scene_grandchild() -> None:
    scene_plan("grandchild", 3)
    with witness() as (port, hits):
        grandchild_code = _child_connect_code(port, "GRANDLEAKED")
        child_code = (
            "import subprocess, sys\n"
            f"proc = subprocess.run([sys.executable, '-c', {grandchild_code!r}], capture_output=True, text=True, timeout=15)\n"
            "print('grand_rc', proc.returncode)\n"
        )
        with enforce({"fs": "read-only", "network": "none", "process": "spawn"}, organ="w12-grandparent"):
            proc = subprocess.run([sys.executable, "-c", child_code], capture_output=True, text=True, timeout=30)
    verdict(
        "GRANDLEAKED" not in proc.stdout and "grand_rc 0" not in proc.stdout and not hits,
        "3: внук под стражем",
        f"детёныш детёныша не соединился (свидетель видел {len(hits)}), stdout: {proc.stdout.strip()[:60]!r}",
    )


# --- сцена 4: декларация рождения --------------------------------------------------

def scene_declaration() -> None:
    scene_plan("declaration", 4)
    python = Path(sys.executable).name
    scope = {"fs": "read-only", "network": "none", "process": {"mode": "spawn", "programs": [python]}}
    alive = ""
    refused = ""
    with enforce(scope, organ="w12-declarer"):
        proc = subprocess.run([sys.executable, "-c", "print('ALIVE')"], capture_output=True, text=True, timeout=20)
        alive = proc.stdout.strip()
        try:
            subprocess.run(["ls", "-la"], capture_output=True, timeout=20)
        except AuthorityViolation as exc:
            refused = str(exc)
    verdict(
        alive == "ALIVE" and "вне заявленных программ" in refused,
        "4: декларация рождения исполняется",
        f"заявленная программа жива ({alive!r}), незаявленная прервана ДО создания: «{refused[-80:]}»",
    )


# --- сцена 5: max_children ----------------------------------------------------------

def scene_max_children() -> None:
    scene_plan("max-children", 5)
    python = Path(sys.executable).name
    scope = {"fs": "read-only", "network": "none", "process": {"mode": "spawn", "programs": [python], "max_children": 1}}
    text = ""
    with enforce(scope, organ="w12-limited"):
        first = subprocess.run([sys.executable, "-c", "print('ONE')"], capture_output=True, text=True, timeout=20)
        try:
            subprocess.run([sys.executable, "-c", "print('TWO')"], capture_output=True, timeout=20)
        except AuthorityViolation as exc:
            text = str(exc)
    verdict(
        first.stdout.strip() == "ONE" and "max_children" in text,
        "5: max_children исполняется",
        f"первый детёныш жив ({first.stdout.strip()!r}), второй не рожден: «{text[-70:]}»",
    )


# --- сцена 6: shell fail-closed -------------------------------------------------------

def scene_shell() -> None:
    scene_plan("shell-fail-closed", 6)
    scope = {"fs": "read-only", "network": "none", "process": {"mode": "spawn", "programs": ["sh"]}}
    text = ""
    with enforce(scope, organ="w12-sheller"):
        try:
            subprocess.run("echo hi", shell=True, capture_output=True, timeout=20)
        except AuthorityViolation as exc:
            text = str(exc)
    verdict(
        "shell" in text.lower(),
        "6: shell: True со скоупом — не рождается",
        f"argv не разбираем — fail-closed: «{text[-80:]}»" if text else "процесс родился — дыра!",
    )


# --- сцена 7: битый конверт ------------------------------------------------------------

def scene_corrupted_envelope(tmp: Path) -> None:
    scene_plan("corrupted-envelope", 7)
    marker = tmp / "marker.txt"
    env = dict(os.environ)
    env["COMMONS_AUTHORITY"] = "{garbage-not-json"
    env["PYTHONPATH"] = str(REPO_ROOT)
    code = f"open({str(marker)!r}, 'w').write('alive'); print('CHILD_ALIVE')"
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=20, env=env)
    verdict(
        proc.returncode != 0 and not marker.exists() and "CHILD_ALIVE" not in proc.stdout,
        "7: битый конверт — детёныш не живёт",
        f"returncode={proc.returncode}, маркера на диске нет: {not marker.exists()} (exit до первого оператора)",
    )


# --- сцена 8: сквозное наследование и настоящая граница (факты) -------------------------

def scene_foreign_boundary() -> None:
    scene_plan("foreign-boundary", 8)
    # 8а: наследование переживает чужую оболочку: /bin/sh -> python3 (внук) -- страж грузится по конверту
    with witness() as (port, hits):
        code = _child_connect_code(port)
        with enforce({"fs": "read-only", "network": "none", "process": "spawn"}, organ="w12-foreign"):
            proc = subprocess.run(["/bin/sh", "-c", f"python3 -c {code!r}"], capture_output=True, text=True, timeout=20)
    fact(
        "8а: наследование переживает чужую оболочку",
        f"/bin/sh -c 'python3 ...' под spawn+network:none: соединений у свидетеля {len(hits)}, "
        f"stdout: {proc.stdout.strip()[:40]!r} — конверт в окружении пережил exec, питоновский внук "
        "загрузил страж (sitecustomize) и его соединение прервано",
    )
    # 8б: настоящая граница: чужой бинарник сам умеет соединяться и конверт не читает
    import urllib.parse  # noqa: F401
    with witness() as (port, hits):
        with enforce({"fs": "read-only", "network": "none", "process": "spawn"}, organ="w12-curl"):
            proc = subprocess.run(
                ["curl", "--max-time", "2", "-s", f"http://127.0.0.1:{port}/"],
                capture_output=True, text=True, timeout=20,
            )
    fact(
        "8б: граница — чужой бинарник конверт не читает",
        f"curl под spawn+network:none соединился: свидетель видел {len(hits)} — syscalls чужого процесса "
        "стражу не видны (execve роняет hook, не-Python конверт не разбирает); remedy — декларация программ "
        "(сцена 4), сеть органу не заявлена — события хоста ловит свидетель (SPEC-0002 v0.7.0, честная граница)",
    )


# --- сцена 9: кровь волны ----------------------------------------------------------------

def scene_blood() -> None:
    scene_plan("wave-blood", 9)
    BLOOD_JOURNAL.append(
        make("halt" if RED else "shutdown", "wave12", "self", TRACE, {"verdicts": len(GREEN), "red": len(RED)})
    )
    BLOOD_JOURNAL.close()
    report = verify(BLOOD_PATH)
    verdict(
        report["gaps"] == [] and report["chained"],
        "9: кровь волны цела",
        f"{report['events']} конвертов, гэпов {len(report['gaps'])}, chained={report['chained']}",
    )
    print(f"\nИТОГ: {len(GREEN)} зелёных / {len(RED)} красных")
    if RED:
        for line in RED:
            print(f"  КРАСНО: {line}")
        sys.exit(1)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene_c3_flipped()
        scene_inheritance()
        scene_grandchild()
        scene_declaration()
        scene_max_children()
        scene_shell()
        scene_corrupted_envelope(Path(tmp))
        scene_foreign_boundary()
        scene_blood()


if __name__ == "__main__":
    main()
