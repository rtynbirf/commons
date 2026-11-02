# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмка SPEC-0002 v0.8.0 «ядерная песочница детёнышей» (волна №13): seccomp-BPF до execve.

Граница волны №12 (v0.7.0): питоновский детёныш живёт под стражем (конверт
COMMONS_AUTHORITY + sitecustomize), но чужой бинарник конверт не читает — его
syscalls не видны («curl соединился живьём» — факт прогона волны №12). v0.8.0:
скоуп process принимает `sandbox: {network: none}` — обёртка Popen передаёт
детёнышу preexec_fn, который ДО execve ставит ядерный seccomp-BPF фильтр
(socket(AF_INET/AF_INET6) → EPERM); фильтр наследуется execve и всеми потомками
независимо от языка — не-python детёныш закрыт ядром так же, как питоновский.

Честные границы: seccomp не ограничивает fs (Landlock — kernel ≥ 5.13, кандидат);
sandbox применяется только при явном заявлении — без него прежняя граница.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from blood.journal import Journal
from synapse.authority import AuthorityViolation, enforce, normalize
from synapse.gateway import Gateway

REPO_ROOT = Path(__file__).resolve().parent.parent
CHILD = Path(sys.executable).name

PROBE_INET = (
    "import socket\n"
    "try:\n"
    "    socket.socket(2, 1); print('INET-LIVE')\n"  # 2 = AF_INET
    "except OSError as e:\n"
    "    print('INET-DENIED', e.errno)\n"
    "try:\n"
    "    socket.socket(1, 1).close(); print('UNIX-LIVE')\n"  # 1 = AF_UNIX
    "except OSError as e:\n"
    "    print('UNIX-DENIED', e.errno)\n"
)

SCOPE_SANDBOX = {"mode": "spawn", "programs": [CHILD], "sandbox": {"network": "none"}}
AUTHORITY_SANDBOX = {"fs": "read-only", "network": "none", "process": SCOPE_SANDBOX}


def run_probe(authority: dict[str, Any], argv: list[str], **kwargs: Any) -> str:
    with enforce(authority, organ="sandbox-probe"):
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=30, **kwargs)
    return proc.stdout.strip()


# --- а) грамматика ---------------------------------------------------------------


def test_sandbox_grammar_is_executable() -> None:
    """`{mode: spawn, programs, sandbox: {network: none}}` — грамматика: sandbox доезжает до стража."""
    out = normalize({"process": dict(SCOPE_SANDBOX)})
    assert out["process"]["sandbox"] == {"network": "none"}, out
    assert out["process"]["programs"] == [CHILD]


@pytest.mark.parametrize("bad", [
    "none",                          # не dict
    {},                              # пустая песочница
    {"network": "any"},              # частичная сеть не исполнена честно — не грамматика
    {"network": "localhost"},        # то же
    {"net": "none"},                 # неизвестный ключ
    {"network": "none", "fs": []},   # лишний ключ
])
def test_bad_sandbox_grammar_rejected(bad: Any) -> None:
    """Fail-closed: кривая песочница — шлюз не стартует (SPEC-0002 п.11)."""
    with pytest.raises(Exception) as exc:
        normalize({"process": {"mode": "spawn", "programs": [CHILD], "sandbox": bad}})
    assert "sandbox" in str(exc.value) or "process" in str(exc.value), str(exc.value)


# --- б) ядро: inet рвётся, unix жив, язык не важен --------------------------------


def test_python_child_inet_denied_kernel() -> None:
    """Детёныш с sandbox: socket(AF_INET) → EPERM от ядра ДО кода детёныша; unix жив."""
    out = run_probe(AUTHORITY_SANDBOX, [sys.executable, "-c", PROBE_INET])
    assert out == "INET-DENIED 1\nUNIX-LIVE", out  # 1 = EPERM


def test_shell_child_inet_denied_kernel() -> None:
    """Ключевой факт волны №13: не-python детёныш (sh -c) закрыт ядром так же — конверт ему и не нужен.
    sh заявлен в programs (декларация при рождении v0.7.0) — но inet-запрет идёт от ЯДРА, не от конверта."""
    scope = {"mode": "spawn", "programs": [CHILD, "sh"], "sandbox": {"network": "none"}}
    argv = ["/bin/sh", "-c", 'exec "$0" -c "$1"', sys.executable, PROBE_INET]
    out = run_probe({"fs": "read-only", "network": "none", "process": scope}, argv)
    assert "INET-DENIED 1" in out and "UNIX-LIVE" in out, out


def test_grandchild_inherits_kernel_filter() -> None:
    """Внук (детёныш детёныша) тоже под ядерным фильтром — seccomp наследуется execve."""
    inner = PROBE_INET.replace("'", "'\\''")  # для вложенного -c
    argv = [sys.executable, "-c", f"import subprocess,sys; print(subprocess.run([sys.executable,'-c',{PROBE_INET!r}],capture_output=True,text=True).stdout.strip())"]
    out = run_probe(AUTHORITY_SANDBOX, argv)
    assert "INET-DENIED 1" in out and "UNIX-LIVE" in out, out


def test_no_sandbox_inet_live_boundary() -> None:
    """Без sandbox — прежняя граница честно на месте: bare spawn, детёныш соединяется (не-python — только свидетель)."""
    out = run_probe({"fs": "read-only", "network": "none", "process": "spawn"}, [sys.executable, "-c", PROBE_INET])
    assert out == "INET-LIVE\nUNIX-LIVE", out


# --- в) слот preexec и шлюз --------------------------------------------------------


def test_preexec_slot_taken_by_guard() -> None:
    """Орган передаёт свой preexec_fn под sandbox — рождение прервано: слот занят стражем (честно названо)."""
    with pytest.raises(AuthorityViolation):
        run_probe(AUTHORITY_SANDBOX, [sys.executable, "-c", "print('x')"], preexec_fn=lambda: None)


def test_gateway_accepts_sandbox_scope(tmp_path: Path, journal: Journal) -> None:
    """Шлюз стартует с sandbox-скоупом: грамматика исполнима (SPEC-0002 п.8)."""
    import yaml

    entry = {
        "name": "sandboxed", "system": "senses", "mode": "dependency",
        "upstream": "https://example.invalid/sandboxed", "license": "MIT",
        "transport": "stdio", "command": "sandboxed-mcp", "healthcheck": "initialize handshake",
        "tools": ["run"], "authority": dict(AUTHORITY_SANDBOX), "adapter": "tests.fakes:FakeEcho",
    }
    path = tmp_path / "mcp-manifest.yaml"
    path.write_text(yaml.safe_dump({"organs": [entry], "substitutions": {}}, allow_unicode=True), encoding="utf-8")
    gateway = Gateway(path, journal)
    assert gateway.manifest_entry("sandboxed")["authority"]["process"]["sandbox"] == {"network": "none"}


def test_house_manifest_marks_children_sandbox(tmp_path: Path, journal: Journal, monkeypatch: pytest.MonkeyPatch) -> None:
    """Дом (волна №13): markitdown — детёныш под ядерной песочницей (родитель network: none);
    browser-use — без sandbox (сеть — его работа); http-органы — process: none."""
    monkeypatch.setenv("DOWNLOADS_DIR", str(tmp_path))  # п.6: без VAR орган не развёрнут — адаптера нет
    gateway = Gateway(REPO_ROOT / "synapse" / "mcp-manifest.yaml", journal)
    by_name = {a.entry.get("name"): a.entry for a in gateway.adapters}
    assert by_name["markitdown"]["authority"]["process"].get("sandbox") == {"network": "none"}
    assert "sandbox" not in by_name["browser-use"]["authority"]["process"], "browser-use ходит в веб — sandbox не его"
    assert by_name["ollama"]["authority"]["process"] == "none"
