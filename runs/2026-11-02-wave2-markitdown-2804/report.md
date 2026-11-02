<!--
SPDX-FileCopyrightText: 2026 COMMONS contributors
SPDX-License-Identifier: Apache-2.0
-->

# Волна № 2: markitdown #2804 — обычный JSON, промаркированный как ноутбук

Дата: 2026-11-02 · Продолжение ROADMAP M3 «Первые патчи, отправленные в upstream-органы»

Итог: **дефект найден, верифицирован в клоне, патч готов (aaf26e7, DCO), красный/зелёный
подтверждён, очередь проверена в момент стрелка**. Гейт: токен волны мёртв — ветка не
пушится в форк, PR не создаётся. Всё застёгнуто до стрелка.

## Условия гона

- Токен №4 мёртв: `GET /user` → **HTTP 401** (отозван или истёк).
- Анонимный API GitHub исчерпан: `0/60` на обоих egress-IP, сброс ≈ 12 ч.
- Маршрут волны перестроен на методы вне рейт-лимита: git-протокол (fetch/клоны)
  и веб-страницы GitHub (WebFetch). Разведка не остановилась.

## Разведка: свежие бесхозные баги microsoft/markitdown

Фильтр `no:linked:pr`, newest first (урок волны-1: очередь — главный фильтр):

| Кандидат | Вердикт |
|---|---|
| #2804 (1 ноя) обычный JSON с маркерами nbformat тихо выбрасывается | **выбран: тихая потеря данных, 0 PR, 0 веток, 0 комментариев** |
| #2781 (28 окт) Atom-фид без entry отклонён | пропущен: в Development уже ветка репортёра «fix(rss): accept Atom feeds that contain zero entries» — не наступаем на чужую работу |
| #2806 (1 ноя) DOCX math: degHide игнорируется | запас |
| #2728 (21 окт) XLSX теряет значения ошибок #DIV/0!, #REF! | запас |
| #2690 (10 окт) фрагменты data-URI декодируются как payload | запас |

## Дефект (верифицирован в клоне, не по дампам)

`IpynbConverter.accepts()` искал подстроки `nbformat` и `nbformat_minor` в любом месте
текста. Обычный JSON, упоминающий маркеры в строковых значениях (или с числовыми
полями без `cells`), маршрутизировался в ноутбучный конвертер; итерация пустых
`cells` возвращала успешный **пустой** результат — документ молча выбрасывался,
не доходя до plain-text конвертера. Репро из бага:

`{"description": "The format uses nbformat and nbformat_minor fields.", "items": ["important content"]}` → `''`.

## Патч

- Worktree `markitdown-w2` (клон общий и грязный правками соседа — не тронут).
- Ветка `fix/ipynb-nbformat-structural-sniff` от `origin/main` (7482c09),
  коммит **aaf26e7** (DCO, автор rtynbirf), +162/−4, 2 файла.
- `_is_notebook_json()`: структурная проверка — JSON-объект (BOM терпит) с числовыми
  `nbformat`/`nbformat_minor` и списком `cells` на верхнем уровне; malformed и
  глубоко-вложенный JSON отклоняются без `RecursionError`; маршруты `.ipynb`
  и BOM-ноутбуков не тронуты.
- 7 новых регресс-тестов в `test_module_misc.py`. Красный/зелёный: **4 теста горят
  на незаквешенном коде, зелёные после фикса** (проверено откатом только src-файла).
- Полный сюит: **1169 passed, 12 skipped, 0 failed**.
- Рядом с отчётом: `0001-fix-ipynb-….patch` (`git am` сохранит автора и DCO),
  `pr-body.md` (готовое тело: Fixes #2804, Summary/Changes/Testing).

## Гейт: токен мёртв, стрелок не потянуть

Проверка очереди «в момент стрелка» (веб, Development-секция): **«No branches or
pull requests»**, комментариев нет — полоса свободна, но:

- push ветки в форк и `POST /pulls` требуют живой токен;
- CLA Microsoft на аккаунте уже подписана (реплай `@microsoft-github-policy-service
  agree` в #2808, `license/cla: success`) — ритуала не будет.

Два пути дожима:

1. Свежий classic-токен (`public_repo`) → волна дожмёт push+PR одним скриптом.
2. Человек: `git push` ветки в форк + compare-URL с телом из `pr-body.md`.

## Соседи

- Рабочая копия `work/markitdown` несёт правки другого агента (.devcontainer,
  .github/…) — не тронуты; волна работала в отдельном worktree.
- commons: чужие правки в полёте; в коммит волны входит только её run-каталог.

## Дожим (токен №5): PR открыт, ритуалов ноль

- Токен №5 (ghp-классика, `public_repo`): ветка `fix/ipynb-nbformat-structural-sniff`
  (aaf26e7) запушена в форк, `POST /repos/microsoft/markitdown/pulls` → **HTTP 201**:
  **microsoft/markitdown#2810** — «fix(ipynb): require notebook structure, not marker
  substrings» (Fixes #2804; head aaf26e7 → main, maintainer_can_modify).
- Очередь на стрелке: поиск по head-ветке — 0 PR; Development у #2804 — пусто.
  Дубликатов нет, полоса чистая.
- **CLA Microsoft сработала аккаунт-вайл**: `license/cla: completed/success` в первый
  же момент, policy-service даже не прокомментировал — реплай `agree` в #2808 закрыл
  вопрос за все будущие волны в органы Microsoft. Волна-2 прошла без единого ручного
  шага человека — от разведки до открытого PR.
- Состояние после дожима: #2810 — open, blocked = только ревью людей; #2808 —
  без движений (ждёт мейнтейнеров); n8n#5689 — в ожидании ревью (проверено ранее).
