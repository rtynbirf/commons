# Орган: ggml-org/llama.cpp

Система: метаболизм · Режим: dependency · Лицензия: MIT (верифицировано GitHub API 2026-11-01)
Статус: m1-адаптер готов — соединение настраивается `LLAMA_SERVER_URL`

## Роль в обмене

Запас метаболизма: инференс C/C++ через `llama-server`. Существует как орган,
чтобы тест отключения ollama был настоящим, а не декларацией.

## Контракт через синапсы

- Вход: `completion` (промпт + n_predict), `embedding` (текст).
- Выход: ответ модели / вектор — в те же поля конверта, что и у ollama.
- Полномочия: `network: localhost-only`, `fs: none`.
- Цена: `tokens_in` ← `tokens_evaluated`, `tokens_out` ← `tokens_predicted`, `seconds` — замер шлюза.

## Адаптер

`synapse/adapters/llamacpp.py:LlamaCppAdapter`. Healthcheck: `GET /health`.

## Тест отключения

Это и есть замена: `substitutions: {ollama: [llama.cpp]}`. Приёмка спайка S1 —
выбор основного метаболизма по метрикам (latency p50/p95, ток/с) на одинаковой модели.

## Обратный поток

Патчи — в https://github.com/ggml-org/llama.cpp. Форк запрещён (ADR-0001).

## Ссылки

- Upstream: https://github.com/ggml-org/llama.cpp
- Реестр: `organs/registry.yaml` · Провенанс: [../../PROVENANCE.md](../../PROVENANCE.md)
