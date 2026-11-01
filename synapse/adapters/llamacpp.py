"""Адаптер llama.cpp (запас метаболизма): llama-server HTTP API.

Healthcheck — GET /health. Инструменты: completion, embedding
(SPEC-0001 G2: замена ollama не меняет цикл — меняется трафик шлюза).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from blood.envelope import Cost


class LlamaCppAdapter:
    """Орган ggml-org/llama.cpp (MIT). Полномочия: network: localhost-only."""

    def __init__(self, entry: dict[str, Any]) -> None:
        self.endpoint = (entry.get("endpoint") or "http://127.0.0.1:8080").rstrip("/")
        self.authority = entry.get("authority") or {}
        self.timeout = 120.0

    def health(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.endpoint}/health", timeout=2.0) as resp:
                return resp.status == 200
        except Exception:  # noqa: BLE001
            return False

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Cost]:
        if tool == "completion":
            data = self._request("POST", "/completion", {
                "prompt": payload.get("prompt", ""),
                "n_predict": payload.get("n_predict", 256),
            })
            cost = Cost(tokens_in=int(data.get("tokens_evaluated", 0)), tokens_out=int(data.get("tokens_predicted", 0)))
            return {"response": data.get("content", "")}, cost
        if tool == "embedding":
            data = self._request("POST", "/embedding", {"content": payload.get("text", "")})
            return {"embedding": data.get("embedding")}, Cost()
        raise ValueError(f"llama.cpp: неизвестный инструмент {tool!r}")

    def _request(self, method: str, route: str, body: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(
            f"{self.endpoint}{route}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method=method,
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
