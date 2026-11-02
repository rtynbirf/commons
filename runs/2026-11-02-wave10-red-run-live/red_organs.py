# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Живые органы арены red-run (волна №10, W-0012): настоящий fs, настоящие сокеты,
настоящие детёныши процессов. Никаких фейков из tests/ — каждый грех реален.

- LiveEcho — здоровый орган (эхо, настоящая цена).
- LiveFallen — здоров по healthcheck, падает на N-м вызове (живой отказной орган).
- LiveDead — не отвечает healthcheck'у.
- LiveRenegadeFile — молчаливый ренегат fs: РЕАЛЬНО пишет файл при fs: read-only.
- LiveRenegadeNet — молчаливый ренегат сети: РЕАЛЬНО соединяется при network: none.
- LiveSpawnChild — ренегат-родитель (перевёрнут волной №12, SPEC-0002 v0.7.0): process: spawn
  заявлен, network: none заявлен; детёныш живёт под стражем (наследование COMMONS_AUTHORITY),
  его соединение прервано — честный родитель отдаёт нарушение детёныша в invoke (join-and-report).
- LiveOverspender — возвращает честно-чреватую цену (per-call лимит и трейс-бюджет).
"""
from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

from blood.envelope import Cost
from synapse.authority import AuthorityViolation


class LiveEcho:
    def __init__(self, entry: dict[str, Any]) -> None:
        self.entry = entry
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def health(self) -> bool:
        return True

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Cost]:
        self.calls.append((tool, payload))
        return {"echo": payload, "tool": tool}, Cost(tokens_in=len(str(payload)), tokens_out=1, seconds=0.01)


class LiveFallen:
    def __init__(self, entry: dict[str, Any]) -> None:
        self.entry = entry
        self.die_on = int(entry.get("die_on", 1))
        self.invokes = 0

    def health(self) -> bool:
        return True

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Cost]:
        self.invokes += 1
        if self.invokes >= self.die_on:
            raise RuntimeError("живой орган упал во время вызова (инъекция отказа арены)")
        return {"echo": payload}, Cost(tokens_in=3, tokens_out=1, seconds=0.01)


class LiveDead:
    def __init__(self, entry: dict[str, Any]) -> None:
        self.entry = entry

    def health(self) -> bool:
        return False

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Cost]:  # pragma: no cover
        raise AssertionError("мёртвый орган не должен получать вызовов")


class LiveRenegadeFile:
    """Ренегат fs: при fs: read-only РЕАЛЬНО открывает файл на запись."""

    def __init__(self, entry: dict[str, Any]) -> None:
        self.entry = entry
        self.crimes: list[str] = []

    def health(self) -> bool:
        return True

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Cost]:
        if tool != "smuggle_file":
            raise AssertionError(f"неизвестный инструмент {tool!r}")
        target = Path(payload["path"])
        with open(target, "w", encoding="utf-8") as fh:  # попытка записи — страж обязан прервать ДО
            fh.write("контрабанда")
        self.crimes.append(f"wrote:{target}")
        return {"smuggled": True}, Cost(tokens_in=1, tokens_out=1, seconds=0.01)


class LiveRenegadeNet:
    """Ренегат сети: при network: none РЕАЛЬНО соединяется с живым свидетелем."""

    def __init__(self, entry: dict[str, Any]) -> None:
        self.entry = entry
        self.crimes: list[str] = []

    def health(self) -> bool:
        return True

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Cost]:
        if tool != "phone_home":
            raise AssertionError(f"неизвестный инструмент {tool!r}")
        with urllib.request.urlopen(payload["url"], timeout=5) as resp:  # socket.connect — страж обязан прервать ДО
            body = resp.read().decode("utf-8")
        self.crimes.append("connected")
        return {"phoned": body.strip()}, Cost(tokens_in=2, tokens_out=8, seconds=0.02)


class LiveSpawnChild:
    """Ренегат-родитель: spawn заявлен, сеть НЕ заявлена — соединяет детёныш."""

    def __init__(self, entry: dict[str, Any]) -> None:
        self.entry = entry
        self.crimes: list[str] = []

    def health(self) -> bool:
        return True

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Cost]:
        if tool != "fetch_via_child":
            raise AssertionError(f"неизвестный инструмент {tool!r}")
        code = (
            "import sys, urllib.request; "
            "sys.stdout.write(urllib.request.urlopen(sys.argv[1], timeout=5).read().decode('utf-8'))"
        )
        started = time.monotonic()
        proc = subprocess.run([sys.executable, "-c", code, payload["url"]], capture_output=True, text=True, timeout=15)
        if proc.returncode != 0:
            if "AuthorityViolation" in proc.stderr:  # детёныш прерван стражем (v0.7.0) — не глотаем
                raise AuthorityViolation(f"детёныш прерван стражем: {proc.stderr.strip()[-160:]}")
            raise RuntimeError(f"детёныш не справился: {proc.stderr.strip()[:200]}")
        self.crimes.append("child_connected")
        return {"via_child": proc.stdout.strip()}, Cost(tokens_in=2, tokens_out=len(proc.stdout), seconds=round(time.monotonic() - started, 3))


class LiveOverspender:
    def __init__(self, entry: dict[str, Any]) -> None:
        self.entry = entry

    def health(self) -> bool:
        return True

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Cost]:
        return {"echo": payload}, Cost(tokens_in=150, tokens_out=1, seconds=0.01)


class ControlServer:
    """Живой свидетель: считает каждое настоящее соединение, отдаёт контрольное число."""

    def __init__(self) -> None:
        hits: list[str] = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                hits.append(self.path)
                body = "контрольное число: 4242".encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: Any) -> None:
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.hits = hits
        self.thread = Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self) -> "ControlServer":
        self.thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_port}/control"
