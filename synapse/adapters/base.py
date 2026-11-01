"""Базовый контракт адаптера органа.

Адаптер — единственная точка соприкосновения тела с upstream-кодом.
Результат всегда пара: (результат, Cost). Без цены вызов недействителен.
"""

from __future__ import annotations

from typing import Any, Protocol

from blood.envelope import Cost


class OrganAdapter(Protocol):
    """Контракт органа внутри синапсов."""

    def __init__(self, entry: dict[str, Any]) -> None:
        """entry — запись из synapse/mcp-manifest.yaml (endpoint/command/authority)."""

    def health(self) -> bool:
        """Healthcheck из манифеста. Не отвечает — орган не получает вызовов."""

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Cost]:
        """Вызов инструмента органа. Возвращает (результат, цена)."""
