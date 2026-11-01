# Орган: microsoft/markitdown

Система: сенсорика · Режим: dependency · Лицензия: MIT (верифицировано GitHub API 2026-11-01)
Статус: m1-адаптер готов — орган поднимается командой `markitdown-mcp` (MCP stdio)

## Роль в обмене

Сенсорика организма: документы (PDF, DOCX, XLSX, …) превращаются в Markdown,
которое понимает ствол мозга. Первое «что происходит снаружи» внутри крови.

## Контракт через синапсы

- Вход: `convert_to_markdown` (путь/URI документа).
- Выход: `{"text": "<markdown>", "is_error": bool}` — в конверт крови.
- Полномочия: `fs: read-only-input-dir`, `network: none` — орган читает только входной каталог.
- Цена: секунды замером; токены 0 (орган их не считает — считать будет метаболизм).

## Адаптер

`synapse/adapters/mcp_stdio.py:MCPStdioAdapter` — универсальный MCP-stdio клиент
(JSON-RPC 2.0, initialize handshake). Healthcheck: initialize handshake.

## Тест отключения

Замен в таблице нет (`substitutions: {markitdown: []}`) — при недоступности орган
не получит вызовов, задача уйдёт в REFLECT с `error`. Заменяемость обеспечивается
универсальностью адаптера: любой MCP-совместимый конвертер подключается правкой манифеста.

## Обратный поток

Патчи — в https://github.com/microsoft/markitdown. Форк запрещён (ADR-0001).

## Ссылки

- Upstream: https://github.com/microsoft/markitdown
- Реестр: `organs/registry.yaml` · Провенанс: [../../PROVENANCE.md](../../PROVENANCE.md)
