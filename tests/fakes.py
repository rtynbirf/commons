"""Фейковые органы для тестов и CI: реальные upstream-сервисы не нужны.

Тест отключения (G2) гоняется здесь на подставках; на машине пользователя
те же сценарии идут через настоящие адаптеры ollama/llama.cpp/MCP-stdio.
"""

from __future__ import annotations

from typing import Any

from blood.envelope import Cost
from synapse.gateway import AuthorityViolation


class FakeEcho:
    """Здоровый орган-эхо: возвращает payload и честную цену."""

    def __init__(self, entry: dict[str, Any]) -> None:
        self.entry = entry
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def health(self) -> bool:
        return True

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Cost]:
        self.calls.append((tool, payload))
        return {"echo": payload, "tool": tool}, Cost(tokens_in=len(str(payload)), tokens_out=1, seconds=0.01)


class FakeDead:
    """Не отвечающий орган: healthcheck провален."""

    def __init__(self, entry: dict[str, Any]) -> None:
        self.entry = entry

    def health(self) -> bool:
        return False

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Cost]:  # pragma: no cover
        raise AssertionError("мёртвый орган не должен получать вызовов")


class FakeFallen:
    """Здоров по healthcheck, но падает при вызове (отказной режим SPEC-0001)."""

    def __init__(self, entry: dict[str, Any]) -> None:
        self.entry = entry

    def health(self) -> bool:
        return True

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Cost]:  # pragma: no cover
        raise RuntimeError("орган упал во время вызова")


class FakeAbuser:
    """Пытается выйти за полномочия → security.violation (SPEC-0002)."""

    def __init__(self, entry: dict[str, Any]) -> None:
        self.entry = entry

    def health(self) -> bool:
        return True

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Cost]:
        raise AuthorityViolation("орган запросил сеть, полномочия: fs: read-only")


class FakeMortal:
    """Здоровый орган-процесс: помнит shutdown (SPEC-0002 п.7) и здоровье."""

    def __init__(self, entry: dict[str, Any]) -> None:
        self.entry = entry
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.shutdowns = 0
        self.healthy = True

    def health(self) -> bool:
        return self.healthy

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Cost]:
        self.calls.append((tool, payload))
        return {"echo": payload, "tool": tool}, Cost(tokens_in=3, tokens_out=1, seconds=0.01)

    def shutdown(self) -> None:
        self.shutdowns += 1


class FakeFlaky:
    """Орган с переворачивающимся healthcheck: ловит циклы замен (SPEC-0002 п.3)."""

    def __init__(self, entry: dict[str, Any]) -> None:
        self.entry = entry
        self.healthy = True

    def health(self) -> bool:
        self.healthy = not self.healthy
        return self.healthy

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Cost]:  # pragma: no cover
        raise AssertionError("в тесте цикла замен вызов не доходит до органа")
