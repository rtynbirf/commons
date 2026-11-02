<!--
SPDX-FileCopyrightText: 2026 COMMONS contributors
SPDX-License-Identifier: Apache-2.0
-->

# Волна № 6: langchain — первая стерильная цель после пяти волн мониторинга

Дата: 2026-11-02 · Продолжение ROADMAP M3 «Первые патчи, отправленные в upstream-органы»

Итог: **langchain#41632 открыт** (fix text-splitters, 1 коммит f0be70d, DCO, mergeable) —
первый POST через иммунитет SPEC-0009 в langchain; второй жанр (#41631) занят — патч-резерв
**5eaaba82** в форке. Агент 6-a погиб («context canceled») — работу довёл интегратор руками;
агент 6-b прошёл полный цикл. Токен №7 проверен и принят (.ghenv).

## Разведка (токен №7)

Свип 48 ч по 10 донорам (агент): стерильные цели нашлись только в langchain —
#41624 (text-splitters, 0 комм./0 PR) и #41631 (core/openai, 0 комм./0 PR).
Ollama-хвост — Go/CUDA/фичи (не песочница); pydantic #14168 — фикс в pydantic-core
(Rust); cpython #161077 — docs, но PSF CLA + автор требует issue-first. Очередь XLSX
markitdown: #2732 (APPROVED) и #2766 (COMMENTED с просьбой guard+тест) живы — дожим
резерва 5aeea96 по-прежнему отложен. Наши PR #5689/#2808/#2810 — человеческих ревью нет.

## Цель A — langchain#41624 (пост: PR #41632)

- **Дефект:** `split_text()` резал `encoded[1:-1]`, предполагая ровно один special-токен
  на каждом конце. Токенайзеры без BOS+EOS (Qwen-эмбеддинги) теряют контент-токены:
  `'Hello' -> []`. Автор issue предложил верный фикс — `add_special_tokens=False`.
- **Красный/зелёный честно:** фейковый токенайзер (без тяжёлых пакетов, sys.modules-патч):
  на неоткаченном коде 3 падения из 6, после фикса 6/6; весь сюит пакета 165 passed;
  ruff check + format чисты.
- **Фикс:** `sentence_transformers.py` — `split_text()` через новый
  `_encode_without_special()`; `count_tokens()` не тронут (констрейнт автора).
- **Иммунитет:** dogfood дважды — до POST `queue-clear`, при POST карта+очередь
  перепроверены (`OK карта … OK очередь … UPSTREAM: PR …`) — PR **#41632**.

## Цель B — langchain#41631 (резерв 5eaaba82)

- **Дефект:** валидный JSON-не-объект в tool-call arguments (`'[]'`, `'3'`) проходил в
  `args` → ValidationError всего `invoke()`; falsy молча превращался в `{}`.
- **Фикс агента 6-b:** 3 точки парсинга (core `default_tool_parser`, `parse_tool_call`,
  partner Responses API), +226/−10, 15 новых тест-кейсов; красный 13/17 → зелёный 17/17,
  core 2453 passed (1 pre-existing failure, не наш), partners/openai 724 passed.
- **Иммунитет:** dogfood вернул **queue-occupied** (#41468, #40147, #39057, #39264) —
  POST отложен, резерв `5eaaba82` (DCO) в форке `rtynbirf/langchain`, дожим одним шагом.
- Нюанс записан: default branch langchain — **master**, не main (первый наш POST туда).

## Уроки

1. Агент может погибнуть молча («sub agent response is empty»): артефакты территории
   (клон на tip, чистый статус) показали, что работа не сделана — интегратор довёл сам,
   не ретраем вслепую, а чтением состояния территории.
2. Ленивый импорт класса спасает тесты: верхнеуровневый `from langchain_text_splitters
   import …` не тянет `sentence_transformers` — ImportError только в `__init__`.
3. Аннотации fixture-параметров у pytest — ловушка с `from __future__ import
   annotations` + TYPE_CHECKING: резолв по имени класса в рантайме недоступен;
   честные верхнеуровневые импорты проще и ruff-чисты.
4. Собственный форк репо создавался впервые (`POST /repos/…/forks`) — механизм занесён.

## Точки мониторинга

- langchain#41632 — CI-матрица langchain долгая; ждём человеческого ревью.
- Резерв 5eaaba82 (#41631) — дожим при очистке жанра tool-call (`--send`).
- Резервы markitdown 5aeea96 (#2728) и a8d1b801 (#12567) — дожим при смерти #2732/#2766
  и #12568; у #2766 ревьюер просит guard+тест — если мейнтейнеры пойдут в наш резерв,
  добавить обе просьбы перед дожимом.
