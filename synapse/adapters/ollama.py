"""Адаптер ollama (метаболизм, M1): HTTP API локального сервера.

Healthcheck — GET /api/tags (по манифесту). Инструменты: list_models,
generate, chat, embeddings. Цена снимается с ответа ollama
(prompt_eval_count → tokens_in, eval_count → tokens_out) и замером секунд.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from blood.envelope import Cost


class OllamaAdapter:
    """Орган ollama/ollama (MIT). Полномочия: network: localhost (SPEC-0002 п.8)."""

    def __init__(self, entry: dict[str, Any]) -> None:
        self.entry = entry  # идентичность (SPEC-0002 п.9): шлюз сверяет entry["name"]
        self.endpoint = (entry.get("endpoint") or "http://127.0.0.1:11434").rstrip("/")
        self.authority = entry.get("authority") or {}
        self.timeout = 120.0

    def health(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.endpoint}/api/tags", timeout=2.0) as resp:
                return resp.status == 200
        except Exception:  # noqa: BLE001 — нет ответа = орган не здоров
            return False

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Cost]:
        if tool == "list_models":
            data = self._request("GET", "/api/tags", None)
            models = [m.get("name") for m in data.get("models", [])]
            return {"models": models}, Cost()

        route, body = self._tool_route(tool, payload)
        data = self._request("POST", route, body)
        cost = Cost(
            tokens_in=int(data.get("prompt_eval_count") or data.get("prompt_eval_n") or 0),
            tokens_out=int(data.get("eval_count") or data.get("eval_n") or 0),
        )
        if tool == "embeddings":
            return {"embedding": data.get("embedding")}, cost
        return {"response": data.get("response") or (data.get("message") or {}).get("content", "")}, cost

    @staticmethod
    def _tool_route(tool: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
        if tool == "generate":
            return "/api/generate", {"model": payload["model"], "prompt": payload.get("prompt", ""), "stream": False}
        if tool == "chat":
            return "/api/chat", {"model": payload["model"], "messages": payload.get("messages", []), "stream": False}
        if tool == "embeddings":
            return "/api/embeddings", {"model": payload["model"], "prompt": payload.get("text", "")}
        raise ValueError(f"ollama: неизвестный инструмент {tool!r}")

    def _request(self, method: str, route: str, body: dict[str, Any] | None) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            f"{self.endpoint}{route}",
            data=data,
            headers={"Content-Type": "application/json"} if data else {},
            method=method,
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
