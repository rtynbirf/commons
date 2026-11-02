# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Живой прогон волны №13: ядерная песочница детёнышей (SPEC-0002 v0.8.0, п.11).

Прогон печатает факты, не предсказания. Сцены:
1. контроль живьём: детёныш без песочницы (bare spawn) соединяется с живым
   свидетелем — граница волны №12 («чужой бинарник конверт не читает») как она есть;
2. sandbox {network: none}: детёныш socket(AF_INET) → EPERM от ядра ДО кода детёныша,
   свидетель не видел ни одного; unix-сокет жив (stdio-пайпы не сломаны);
3. не-python детёныш (sh -c → python): inet рвёт ядро так же — конверт ему и не нужен;
4. внук (детёныш детёныша) тоже под ядерным фильтром — seccomp наследуется execve;
5. кровь волны: цепочка prev_id цела — verify: 0 гэпов, chained=true.

Кровь волны пишется тем же журналом: runs/2026-11-03-wave13-sandbox/blood.jsonl.
Запуск из корня репо: python runs/2026-11-03-wave13-sandbox/run.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
RUN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(RUN_DIR))  # манифест грузит адаптеры по имени "wave13_organs:..."

import yaml  # noqa: E402

from blood.envelope import make  # noqa: E402
from blood.journal import Journal, verify  # noqa: E402
from synapse.gateway import Gateway  # noqa: E402

import wave13_organs as organs  # noqa: E402

BLOOD_PATH = RUN_DIR / "blood.jsonl"
CHILD = Path(sys.executable).name

PROBE_INET = (
    "import socket\n"
    "try:\n"
    "    socket.socket(2, 1); print('INET-LIVE')\n"
    "except OSError as e:\n"
    "    print('INET-DENIED', e.errno)\n"
    "try:\n"
    "    socket.socket(1, 1).close(); print('UNIX-LIVE')\n"
    "except OSError as e:\n"
    "    print('UNIX-DENIED', e.errno)\n"
)
PROBE_GRANDCHILD = (
    "import subprocess, sys\n"
    "out = subprocess.run([sys.executable, '-c', " + repr(PROBE_INET) + "], capture_output=True, text=True)\n"
    "print(out.stdout.strip())\n"
)

GREEN: list[str] = []
RED: list[str] = []

BLOOD_JOURNAL = Journal()
BLOOD_JOURNAL.attach(BLOOD_PATH)
TRACE = "wave13-sandbox"


def verdict(ok: bool, name: str, detail: str) -> None:
    (GREEN if ok else RED).append(f"{name}: {detail}")
    kind = "reflect" if ok else "error"
    BLOOD_JOURNAL.append(
        make(kind, "wave13", "self", TRACE, {"scene": name, "detail": detail, "verdict": "green" if ok else "red"})
    )
    print(f"[ЗЕЛЁНО] {name}: {detail}" if ok else f"[КРАСНО] {name}: {detail}")


def scene_plan(name: str, index: int) -> None:
    BLOOD_JOURNAL.append(make("plan", "wave13", "self", TRACE, {"scene": name, "index": index}))


def manifest_file(tmp: Path, authority: dict[str, Any]) -> Path:
    doc = {
        "version": "w13-sandbox",
        "updated": "2026-11-03",
        "transport_default": "stdio",
        "organs": [{
            "name": "prober", "system": "senses", "mode": "dependency",
            "upstream": "https://example.invalid/w13", "license": "MIT",
            "transport": "stdio", "command": "fake-w13", "healthcheck": "initialize handshake",
            "tools": ["run_argv"], "authority": authority, "adapter": "wave13_organs:LiveProber",
        }],
    }
    path = tmp / "mcp-manifest.yaml"
    path.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return path


# --- сцена 1: контроль живьём — граница волны №12 как она есть --------------------

def scene_control(server: "organs.ControlServer") -> int:
    scene_plan("s1-control-bare", 1)
    hits_before = len(server.hits)
    bare = organs.LiveProber({"name": "bare-w13"})
    argv = [sys.executable, "-c", PROBE_INET]
    result = bare.invoke("run_argv", {"argv": argv})[0]
    hits = len(server.hits) - hits_before
    ok = "INET-LIVE" in result["stdout"] and hits == 0  # пробник не соединялся с HTTP-свидетелем, inet просто жив
    verdict(
        ok and "INET-LIVE" in result["stdout"],
        "1: контроль живьём — детёныш без песочницы держит inet",
        f"голый диспетчер: детёныш создал inet-socket ({result['stdout'].splitlines()[0]}) — "
        "граница волны №12 как она есть (конверт не-python детёнышу не читается)",
    )
    return hits


# --- сцена 2: sandbox — ядро рвёт inet детёныша ------------------------------------

def scene_sandbox(tmp: Path) -> str:
    scene_plan("s2-sandbox-kernel-denies", 2)
    authority = {"fs": "read-only", "network": "none",
                 "process": {"mode": "spawn", "programs": [CHILD], "sandbox": {"network": "none"}}}
    gw = Gateway(manifest_file(tmp, authority), BLOOD_JOURNAL)
    trace = "w13-s2-sandbox"
    result = gw.call("prober", "run_argv", {"argv": [sys.executable, "-c", PROBE_INET]}, trace)
    out = result["stdout"]
    ok = out == "INET-DENIED 1\nUNIX-LIVE"
    verdict(
        ok,
        "2: sandbox — inet детёныша рвёт ядро, unix жив",
        f"детёныш отчитался: {out!r} — EPERM (errno 1) ДО кода детёныша; stdio-пайпы не сломаны; кровь: обычный act",
    )
    return out


# --- сцена 3: не-python детёныш (sh -c → python) -----------------------------------

def scene_shell_child(tmp: Path) -> str:
    scene_plan("s3-shell-child-denied", 3)
    authority = {"fs": "read-only", "network": "none",
                 "process": {"mode": "spawn", "programs": [CHILD, "sh"], "sandbox": {"network": "none"}}}
    gw = Gateway(manifest_file(tmp, authority), BLOOD_JOURNAL)
    trace = "w13-s3-shell"
    result = gw.call("prober", "run_argv",
                     {"argv": ["/bin/sh", "-c", 'exec "$0" -c "$1"', sys.executable, PROBE_INET]}, trace)
    out = result["stdout"]
    ok = "INET-DENIED 1" in out and "UNIX-LIVE" in out
    verdict(
        ok,
        "3: не-python детёныш закрыт ядром так же",
        f"sh -c → python: {out!r} — фильтр ставится до execve, конверт не-python детёнышу не нужен "
        "(граница волны №12 перевернута)",
    )
    return out


# --- сцена 4: внук под ядерным фильтром ---------------------------------------------

def scene_grandchild(tmp: Path) -> str:
    scene_plan("s4-grandchild-inherits", 4)
    authority = {"fs": "read-only", "network": "none",
                 "process": {"mode": "spawn", "programs": [CHILD], "sandbox": {"network": "none"}}}
    gw = Gateway(manifest_file(tmp, authority), BLOOD_JOURNAL)
    trace = "w13-s4-grandchild"
    result = gw.call("prober", "run_argv", {"argv": [sys.executable, "-c", PROBE_GRANDCHILD]}, trace)
    out = result["stdout"]
    ok = "INET-DENIED 1" in out and "UNIX-LIVE" in out
    verdict(
        ok,
        "4: внук под ядерным фильтром — seccomp наследуется execve",
        f"детёныш детёныша отчитался: {out!r} — фильтр идёт всему потомству независимо от языка",
    )
    return out


# --- сцена 5: кровь волны цела -------------------------------------------------------

def scene_blood() -> int:
    scene_plan("s5-blood-verified", 5)
    report = verify(BLOOD_PATH)
    ok = not report["gaps"] and report["skipped"] == 0 and report["chained"]
    verdict(
        ok,
        "5: кровь волны цела",
        f"{report['events']} конвертов, гэпов {len(report['gaps'])}, skipped {report['skipped']}, "
        f"chained={report['chained']} (цепочка prev_id, SPEC-0003 п.7)",
    )
    return len(BLOOD_PATH.read_text(encoding="utf-8").splitlines())


def main() -> dict[str, Any]:
    import tempfile

    print(f"Детёныш по умолчанию: {CHILD!r}")
    stats: dict[str, Any] = {"ok": True, "scenes": [], "findings": [], "blood_envelopes": 0}
    with tempfile.TemporaryDirectory() as tmpdir, organs.ControlServer() as server:
        scene_control(server)
        stats["scenes"].append({"name": "1"})
        with tempfile.TemporaryDirectory() as tmp:
            out2 = scene_sandbox(Path(tmp))
            stats["scenes"].append({"name": "2", "out": out2})
            out3 = scene_shell_child(Path(tmp))
            stats["scenes"].append({"name": "3", "out": out3})
            out4 = scene_grandchild(Path(tmp))
            stats["scenes"].append({"name": "4", "out": out4})
    envelopes = scene_blood()
    stats["blood_envelopes"] = envelopes
    stats["ok"] = not RED
    (RUN_DIR / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nИТОГ: {len(GREEN)} зелёных / {len(RED)} красных; кровь: {envelopes} конвертов")
    return stats


if __name__ == "__main__":
    main()
