"""Универсальный адаптер органов с транспортом stdio (MCP).

Подходит для markitdown-mcp и browser-use-mcp: новый орган этого класса
подключается правкой манифеста (command + tools), без кода шлюза.
Протокол: JSON-RPC 2.0 по строкам (line-delimited), initialize handshake.
Цена: секунды замером; токены 0 — орган их не считает.
"""

from __future__ import annotations

import json
import selectors
import subprocess
from typing import Any

from blood.envelope import Cost

INIT_TIMEOUT = 15.0
CALL_TIMEOUT = 300.0


class MCPStdioAdapter:
    """Орган-процесс, говорящий по MCP stdio. Полномочия — из манифеста.

    Таймауты (SPEC-0002 п.7): `timeouts: {init, call}` в записи манифеста (секунды);
    зависший орган обнаруживается, процесс завершается самим адаптером.
    Реализация ожидания — POSIX selectors; вне Linux гарантии таймаутов ограничены.
    """

    def __init__(self, entry: dict[str, Any]) -> None:
        self.command: list[str] = entry["command"] if isinstance(entry["command"], list) else [entry["command"]]
        self.authority = entry.get("authority") or {}
        timeouts = entry.get("timeouts") or {}
        self.init_timeout = float(timeouts.get("init", INIT_TIMEOUT))
        self.call_timeout = float(timeouts.get("call", CALL_TIMEOUT))
        self._proc: subprocess.Popen[str] | None = None
        self._next_id = 1

    # --- процесс и handshake ---

    def _ensure_process(self) -> subprocess.Popen[str]:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        self._proc = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self._rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "commons-synapse", "version": "0.3.0"},
        }, timeout=self.init_timeout)
        self._notify("notifications/initialized", {})
        return self._proc

    def _readline(self, proc: subprocess.Popen[str], timeout: float) -> str:
        """Строка из stdout органа с честным таймаутом (SPEC-0002 п.7).

        Таймаут реален: селектор ждёт готовность потока; тишина дольше
        лимита = зависший орган → процесс завершается, исключение наружу.
        """
        sel = selectors.DefaultSelector()
        try:
            sel.register(proc.stdout, selectors.EVENT_READ)
            ready = sel.select(timeout)
            if not ready:
                self._kill(f"нет ответа за {timeout:.1f} c")
                raise TimeoutError(
                    f"MCP stdio: орган {self.command} молчит {timeout:.1f} c — процесс завершён"
                )
            return proc.stdout.readline()
        finally:
            sel.close()

    def _rpc(self, method: str, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        proc = self._ensure_process()
        assert proc.stdin is not None and proc.stdout is not None
        request_id = self._next_id
        self._next_id += 1
        line = json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}, ensure_ascii=False)
        proc.stdin.write(line + "\n")
        proc.stdin.flush()
        while True:
            raw = self._readline(proc, timeout)
            if not raw:
                raise ConnectionError(f"MCP stdio: процесс {self.command} закрыл поток")
            message = json.loads(raw)
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(f"MCP stdio: {method}: {message['error']}")
                return message.get("result", {})

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        proc = self._ensure_process()
        assert proc.stdin is not None
        line = json.dumps({"jsonrpc": "2.0", "method": method, "params": params}, ensure_ascii=False)
        proc.stdin.write(line + "\n")
        proc.stdin.flush()

    # --- контракт органа ---

    def health(self) -> bool:
        try:
            self._ensure_process()
            return True
        except Exception:  # noqa: BLE001 — не стартовал/завис = не здоров
            return False

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Cost]:
        result = self._rpc("tools/call", {"name": tool, "arguments": payload}, timeout=self.call_timeout)
        content = result.get("content") or []
        text = "\n".join(
            block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"
        )
        return {"text": text, "is_error": bool(result.get("isError", False))}, Cost()

    def shutdown(self) -> None:
        """SPEC-0002 п.7: орган-процесс умирает по вызову организма (SIGTERM → SIGKILL)."""
        self._kill("shutdown организма")

    def _kill(self, why: str) -> None:
        proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5.0)

    def __del__(self) -> None:  # noqa: D105 — последняя защита от сирот
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
