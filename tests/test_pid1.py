"""Приёмка SPEC-0004: PID 1 — живой организм.

Boot → HEARTBEAT → Shutdown: один trace_id (G1), смерть с записью (G4),
человек-инициатор (G5), одиночность через lock (G6), органы-процессы
умирают по shutdown() (SPEC-0002 п.7), зависший орган ловится таймаутом.
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import yaml

from blood.envelope import Cost, validate
from blood.pidlock import PIDLock
from brainstem import Budget, PID1
from synapse.adapters.mcp_stdio import MCPStdioAdapter
from synapse.gateway import Gateway, OrganUnavailable
from tests.fakes import FakeMortal

from .conftest import MANIFEST  # noqa: TID252


@pytest.fixture()
def lock_path(tmp_path: Path) -> Path:
    return tmp_path / "runs" / ".pid1.lock"


@pytest.fixture()
def run_dir(tmp_path: Path) -> Path:
    return tmp_path / "runs" / "day-pid1"


def organism(gateway, journal, lock_path: Path, run_dir: Path, **kwargs) -> PID1:
    defaults = dict(interval=0.01, lock=PIDLock(lock_path), run_dir=run_dir)
    defaults.update(kwargs)
    return PID1(gateway, journal, **defaults)


# --- G1: сессия трассируема ---


def test_boot_beats_shutdown_single_trace(gateway, journal, lock_path, run_dir) -> None:
    code = organism(gateway, journal, lock_path, run_dir).run(max_beats=2)
    assert code == 0
    events = journal.all()
    types = [e["type"] for e in events]
    assert types[0] == "boot" and types[-1] == "shutdown"
    assert types.count("boot") == 1 and types.count("shutdown") == 1
    assert len({e["trace_id"] for e in events}) == 1
    health = [e for e in events if e["type"] == "organ.health"]
    assert len(health) == 2 * len(gateway.organ_names)
    assert all(e["source"] == "pid1" for e in events if e["type"] in {"boot", "shutdown", "organ.health"})


def test_every_envelope_valid_and_file_equals_memory(gateway, journal, lock_path, run_dir) -> None:
    """Кровь пишется в момент события: файл == память (SPEC-0004 п.5)."""
    organism(gateway, journal, lock_path, run_dir).run(max_beats=2)
    lines = (run_dir / "blood.jsonl").read_text(encoding="utf-8").splitlines()
    file_events = [json.loads(line) for line in lines if line.strip()]
    assert len(file_events) == len(journal.all())
    for event in file_events:
        validate(event)
    assert {e["trace_id"] for e in file_events} == {journal.all()[0]["trace_id"]}


def test_blood_append_only_across_sessions(gateway, journal, lock_path, run_dir) -> None:
    """Сессии одного дня — один файл, различаются trace_id; перезаписи нет."""
    organism(gateway, journal, lock_path, run_dir).run(max_beats=1)
    organism(gateway, journal, lock_path, run_dir).run(max_beats=1)
    lines = (run_dir / "blood.jsonl").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines if line.strip()]
    traces = {e["trace_id"] for e in events}
    assert len(traces) == 2
    assert len([e for e in events if e["type"] == "boot"]) == 2
    for event in events:
        validate(event)


# --- G4: смерть с записью ---


def test_sigterm_recorded_as_shutdown(gateway, journal, lock_path, run_dir) -> None:
    """Сигнал человека перехватывается: shutdown(signal:SIGTERM), а не тихая смерть."""
    living = organism(gateway, journal, lock_path, run_dir, interval=30.0)

    def _shoot() -> None:
        time.sleep(0.05)
        living.request_shutdown("signal:SIGTERM")

    shooter = threading.Thread(target=_shoot, daemon=True)
    shooter.start()
    code = living.run()  # interval=30: биение есть, сон прерывается запросом
    shooter.join()
    assert code == 0
    shutdown = journal.by_type("shutdown")[-1]
    assert shutdown["payload"]["reason"] == "signal:SIGTERM"
    assert shutdown["payload"]["beats"] == 1


def test_children_shutdown_called(gateway, journal, lock_path, run_dir) -> None:
    """SPEC-0002 п.7: органы-процессы умирают по shutdown(), не сиротами."""
    mortals = {name: FakeMortal(gateway.manifest_entry(name)) for name in ("sense-a", "reserve-c", "fallen-d")}
    for name, mortal in mortals.items():
        gateway.bind_adapter(name, mortal)
    organism(gateway, journal, lock_path, run_dir).run(max_beats=1)
    assert all(mortal.shutdowns == 1 for mortal in mortals.values())


def test_report_written_with_trace(gateway, journal, lock_path, run_dir) -> None:
    organism(gateway, journal, lock_path, run_dir).run(max_beats=1)
    reports = list(run_dir.glob("report-*.md"))
    assert len(reports) == 1
    trace_id = journal.all()[0]["trace_id"]
    text = reports[0].read_text(encoding="utf-8")
    assert trace_id in text
    assert "shutdown" in text


# --- G6: одиночность ---


def test_second_instance_gets_veto(gateway, journal, lock_path, run_dir) -> None:
    """Живой владелец lock: второй организм получает veto и умирает по-записанному."""
    first = PIDLock(lock_path)
    first.acquire()
    try:
        code = organism(gateway, journal, lock_path, run_dir).run(max_beats=1)
        assert code == 1
        types = [e["type"] for e in journal.all()]
        assert types == ["veto", "shutdown"]
        assert journal.by_type("shutdown")[0]["payload"]["reason"] == "second_instance"
        assert not journal.by_type("boot")
    finally:
        first.release()


def test_stale_lock_replaced(gateway, journal, lock_path, run_dir) -> None:
    """Протухший lock (владелец мёртв) заменяется — тело не запирают за мёртвыми."""
    dead = subprocess.Popen(["true"])
    dead.wait()  # pid существует и уже мёртв
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps({"pid": dead.pid, "ts": "2026-11-02T00:00:00+00:00", "path": str(lock_path)}),
        encoding="utf-8",
    )
    code = organism(gateway, journal, lock_path, run_dir).run(max_beats=1)
    assert code == 0
    assert journal.by_type("boot")


# --- G3: бюджет ---


def test_budget_exit_code_2(gateway, journal, lock_path, run_dir) -> None:
    code = organism(
        gateway, journal, lock_path, run_dir, interval=0.01, budget=Budget(seconds=1e-9)
    ).run(max_beats=5)
    assert code == 2
    shutdown = journal.by_type("shutdown")[-1]
    assert shutdown["payload"]["reason"].startswith("budget:")
    assert journal.by_type("organ.health")  # хотя бы одно биение успело случиться


def test_budget_boundary_is_inclusive() -> None:
    """Проведённое ровно в лимит = исчерпан (граница включена)."""
    assert Budget(seconds=1.0).exhausted_by(Cost(seconds=1.0)) is not None
    assert Budget(seconds=1.0).exhausted_by(Cost(seconds=0.999)) is None


# --- SPEC-0002 п.7: зависший орган ---


def test_mcp_stdio_init_timeout_kills_process() -> None:
    entry = {"command": [sys.executable, "-c", "import time; time.sleep(60)"], "timeouts": {"init": 0.2, "call": 1.0}}
    adapter = MCPStdioAdapter(entry)
    started = time.monotonic()
    assert adapter.health() is False  # тишина 60 c обнаружена за 0.2 c
    assert time.monotonic() - started < 5.0
    assert adapter._proc is None  # зависший процесс завершён самим адаптером


def test_mcp_stdio_call_timeout() -> None:
    server = (
        "import sys, json, time;"
        "sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {}}) + '\\n');"
        "sys.stdout.flush(); time.sleep(60)"
    )
    entry = {"command": [sys.executable, "-c", server], "timeouts": {"init": 2.0, "call": 0.3}}
    adapter = MCPStdioAdapter(entry)
    with pytest.raises(TimeoutError):
        adapter.invoke("convert_to_markdown", {"uri": "file:///dev/null"})


# --- SPEC-0002 п.3: циклы замен ---


class FlipFalse:
    """Healthcheck: первый вызов False (для начала цикла с x)."""

    def __init__(self, entry: dict) -> None:
        self.healthy = True

    def health(self) -> bool:
        self.healthy = not self.healthy
        return self.healthy


class FlipTrue:
    """Healthcheck: первый вызов True (для ответа y в цикле)."""

    def __init__(self, entry: dict) -> None:
        self.healthy = False

    def health(self) -> bool:
        self.healthy = not self.healthy
        return self.healthy


def test_substitution_cycle_detected(tmp_path, journal) -> None:
    """Цикл x ↔ y в substitutions не вешает шлюз: OrganUnavailable + error «цикл замен»."""
    manifest = {
        "version": "0.3.0",
        "organs": [
            {
                "name": name,
                "system": "senses",
                "mode": "dependency",
                "upstream": f"https://example.invalid/{name}",
                "license": "MIT",
                "transport": "stdio",
                "command": f"fake-{name}",
                "healthcheck": "initialize handshake",
                "tools": ["echo"],
                "authority": {"fs": "none", "network": "none"},
                "adapter": f"tests.test_pid1:{cls}",
            }
            for name, cls in (("x", "FlipFalse"), ("y", "FlipTrue"))
        ],
        "substitutions": {"x": ["y"], "y": ["x"]},
    }
    path = tmp_path / "cycle-manifest.yaml"
    path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    gateway = Gateway(path, journal)
    with pytest.raises(OrganUnavailable):
        gateway.call("x", "echo", {"data": 1}, "cycle-1")
    errors = journal.by_type("error")
    assert any("цикл замен" in e["payload"]["reason"] for e in errors)
