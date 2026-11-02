# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмка SPEC-0002 v0.7.0 «детёныши процессов» (волна №12): наследование, декларация, fail-closed.

Красная находка С3 волны №10: audit hook живёт в своём процессе и умирает на execve —
ренегат-родитель (`process: spawn` законен, `network: none` заявлен) выводил сеть через
питоновского детёныша, в крови обычный `act`, свидетель видел соединение. Эти тесты
фиксируют КОНТРАКТ спеки: детёныш наследует полномочия органа (конверт COMMONS_AUTHORITY,
загрузка sitecustomize), рождение декларируется скоупом, битый конверт — детёныш не живёт.

Свидетель — живой TCP-сервер: считает каждое настоящее соединение детёныша.
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
from typing import Any, Iterator

import pytest
import yaml

from blood.journal import Journal
from synapse.authority import AuthorityViolation, enforce
from synapse.gateway import Gateway

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


def _child_connect_code(port: int, marker: str = "LEAKED") -> str:
    return (
        f"import socket; s=socket.create_connection(('127.0.0.1', {port}), timeout=3); "
        f"s.sendall(b'leak'); s.close(); print({marker!r})"
    )


def _organ(name: str, *, adapter: str, tools: list[str], authority: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "system": "senses",
        "mode": "dependency",
        "upstream": f"https://example.invalid/{name}",
        "license": "MIT",
        "transport": "stdio",
        "command": f"{name}-mcp",
        "healthcheck": "initialize handshake",
        "tools": tools,
        "authority": authority,
        "adapter": adapter,
    }


def _gateway(tmp_path: Path, journal: Journal, organs: list[dict[str, Any]]) -> Gateway:
    path = tmp_path / "mcp-manifest.yaml"
    path.write_text(
        yaml.safe_dump({"organs": organs, "substitutions": {}}, allow_unicode=True),
        encoding="utf-8",
    )
    return Gateway(path, journal)


# --- a) находка С3 перевернута: питоновский детёныш под стражем ----------------


def test_python_child_blocked_from_network() -> None:
    """Детёныш наследует страж: соединение при network: none прервано в детёныше, свидетель чист (п.8 v0.7.0)."""
    with witness() as (port, hits):
        code = _child_connect_code(port)
        with enforce(dict(SPAWN_NET_NONE), organ="parent-renegade"):
            proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=20)

    assert "LEAKED" not in proc.stdout, f"детёныш соединился: {proc.stdout!r}"
    assert proc.returncode != 0, "детёныш обязан умереть от стража"
    assert "AuthorityViolation" in proc.stderr, f"в детёныше не страж: {proc.stderr[-200:]!r}"
    assert hits == [], f"свидетель видел соединений: {len(hits)} — находка С3 не перевернута"


# --- b) шлюз: честный родитель отдаёт нарушение детёныша в кровь ---------------


def test_gateway_parent_reports_child_violation(tmp_path: Path, journal: Journal) -> None:
    """Приёмка: ренегат-родитель прерван через детёныша, честный орган отдаёт security.violation, не act."""
    with witness() as (port, hits):
        gateway = _gateway(
            tmp_path,
            journal,
            [_organ("parent", adapter="tests.fakes:FakeParentRenegade", tools=["fetch_via_child"], authority=dict(SPAWN_NET_NONE))],
        )
        from tests.fakes import FakeParentRenegade  # noqa: TID252

        with pytest.raises(AuthorityViolation):
            gateway.call("parent", "fetch_via_child", {"port": port}, "w12-c3")

        violations = journal.by_type("security.violation")
    assert len(violations) == 1 and violations[0]["organ"] == "parent"
    assert violations[0]["trace_id"] == "w12-c3"
    assert not journal.by_type("act"), "нарушенный вызов не должен попадать в кровь как act"
    assert hits == [], "свидетель видел соединение детёныша"


# --- c) декларация: заявленная программа жива, незаявленная не рождается -------


def test_declared_program_alive_under_scope() -> None:
    """Скоуп process {mode: spawn, programs}: заявленная программа детёнышем живёт (п.8 v0.7.0)."""
    scope = {"fs": "read-only", "network": "none", "process": {"mode": "spawn", "programs": [Path(sys.executable).name]}}
    with enforce(scope, organ="scoped"):
        proc = subprocess.run([sys.executable, "-c", "print('ALIVE')"], capture_output=True, text=True, timeout=20)
    assert proc.returncode == 0 and "ALIVE" in proc.stdout, f"заявленная программа не родилась: {proc.stderr[-160:]!r}"


def test_undeclared_program_not_born() -> None:
    """Незаявленная программа не рождается: прервано ДО создания процесса, текст называет правило (п.8 v0.7.0)."""
    scope = {"fs": "read-only", "network": "none", "process": {"mode": "spawn", "programs": [Path(sys.executable).name]}}
    with enforce(scope, organ="scoped"):
        with pytest.raises(AuthorityViolation) as exc_info:
            subprocess.run(["ls", "-la"], capture_output=True, timeout=20)
    text = str(exc_info.value)
    assert "вне заявленных программ" in text, f"текст нарушения не называет правило: {text!r}"


def test_max_children_enforced() -> None:
    """max_children: первый детёныш жив, второй — прерван до создания (п.8 v0.7.0)."""
    scope = {
        "fs": "read-only",
        "network": "none",
        "process": {"mode": "spawn", "programs": [Path(sys.executable).name], "max_children": 1},
    }
    with enforce(scope, organ="limited"):
        first = subprocess.run([sys.executable, "-c", "print('ONE')"], capture_output=True, text=True, timeout=20)
        assert first.returncode == 0 and "ONE" in first.stdout, "первый детёныш обязан жить"
        with pytest.raises(AuthorityViolation) as exc_info:
            subprocess.run([sys.executable, "-c", "print('TWO')"], capture_output=True, timeout=20)
    assert "max_children" in str(exc_info.value), f"текст не называет правило: {exc_info.value!r}"


def test_shell_true_rejected_under_scope() -> None:
    """shell: True со скоупом process — не грамматика исполнения: argv не разбираем (fail-closed, п.8 v0.7.0)."""
    scope = {"fs": "read-only", "network": "none", "process": {"mode": "spawn", "programs": ["sh"]}}
    with enforce(scope, organ="shelled"):
        with pytest.raises(AuthorityViolation) as exc_info:
            subprocess.run("echo hi", shell=True, capture_output=True, timeout=20)
    assert "shell" in str(exc_info.value).lower(), f"текст не называет причину: {exc_info.value!r}"


def test_gateway_accepts_process_scope(tmp_path: Path, journal: Journal) -> None:
    """Грамматика скоупа process исполнима: шлюз стартует с {mode: spawn, programs, max_children} (п.8 v0.7.0)."""
    scope = {"fs": "read-only", "network": "none", "process": {"mode": "spawn", "programs": [Path(sys.executable).name], "max_children": 2}}
    gateway = _gateway(tmp_path, journal, [_organ("scoped", adapter="tests.fakes:FakeEcho", tools=["echo"], authority=scope)])
    result = gateway.call("scoped", "echo", {"n": 1}, "w12-grammar")
    assert result["echo"] == {"n": 1}


def test_process_scope_bad_grammar_fails_closed(tmp_path: Path, journal: Journal) -> None:
    """Кривая грамматика скоупа process — шлюз не стартует (fail-closed): programs пуст, mode кривой."""
    bad = {"fs": "read-only", "network": "none", "process": {"mode": "spawn", "programs": []}}
    with pytest.raises(Exception, match="programs"):
        _gateway(tmp_path, journal, [_organ("bad", adapter="tests.fakes:FakeEcho", tools=["echo"], authority=bad)])
    bad_mode = {"fs": "read-only", "network": "none", "process": {"mode": "none", "programs": ["ls"]}}
    with pytest.raises(Exception, match="mode"):
        _gateway(tmp_path, journal, [_organ("bad2", adapter="tests.fakes:FakeEcho", tools=["echo"], authority=bad_mode)])


# --- d) конверт полномочий: загрузка детёныша -----------------------------------


def test_valid_envelope_child_boots_guarded() -> None:
    """Конверт в окружении: детёныш загружает страж (sitecustomize) и подчиняется ему (п.8 v0.7.0)."""
    envelope = json.dumps({"organ": "env-child", "authority": SPAWN_NET_NONE})
    env = dict(os.environ)
    env["COMMONS_AUTHORITY"] = envelope
    env["PYTHONPATH"] = str(REPO_ROOT)
    with witness() as (port, hits):
        code = _child_connect_code(port)
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=20, env=env)
    assert "LEAKED" not in proc.stdout
    assert proc.returncode != 0 and "AuthorityViolation" in proc.stderr
    assert hits == [], "детёныш с конвертом соединился — загрузка не работает"


def test_corrupted_envelope_child_does_not_live(tmp_path: Path) -> None:
    """Битый конверт — детёныш не живёт: exit до первого оператора (fail-closed, п.8 v0.7.0)."""
    marker = tmp_path / "marker.txt"
    env = dict(os.environ)
    env["COMMONS_AUTHORITY"] = "{garbage-not-json"
    env["PYTHONPATH"] = str(REPO_ROOT)
    code = f"open({str(marker)!r}, 'w').write('alive'); print('CHILD_ALIVE')"
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=20, env=env)
    assert proc.returncode != 0, "битый конверт обязан убить детёныша до работы"
    assert "CHILD_ALIVE" not in proc.stdout
    assert not marker.exists(), "детёныш с битым конвертом поработал"


# --- e) внук наследует тем же механизмом ----------------------------------------


def test_grandchild_inherits() -> None:
    """Внук (детёныш детёныша) тоже под стражем: соединение прервано, свидетель чист (п.8 v0.7.0)."""
    with witness() as (port, hits):
        grandchild_code = _child_connect_code(port, "GRANDLEAKED")
        child_code = (
            "import subprocess, sys\n"
            f"proc = subprocess.run([sys.executable, '-c', {grandchild_code!r}], capture_output=True, text=True, timeout=15)\n"
            "print('grand_rc', proc.returncode)\n"
            "print('grand_out', proc.stdout.strip())\n"
        )
        with enforce(dict(SPAWN_NET_NONE), organ="grandparent"):
            proc = subprocess.run([sys.executable, "-c", child_code], capture_output=True, text=True, timeout=30)
    assert "GRANDLEAKED" not in proc.stdout, f"внук соединился: {proc.stdout!r}"
    assert "grand_rc 1" in proc.stdout or "grand_rc" in proc.stdout and "grand_rc 0" not in proc.stdout, proc.stdout
    assert hits == [], f"свидетель видел соединений внука: {len(hits)}"


# --- f) граница действия: рождение вне стража не тронуто (не дыра) --------------


def test_spawn_outside_guard_untouched() -> None:
    """Граница действия (п.8 v0.7.0): детёныш, рождённый вне стража, конверта не получает — обычный код жив."""
    proc = subprocess.run([sys.executable, "-c", "print('FREE')"], capture_output=True, text=True, timeout=20)
    assert proc.returncode == 0 and "FREE" in proc.stdout
