<!--
SPDX-FileCopyrightText: 2026 COMMONS contributors
SPDX-License-Identifier: Apache-2.0
-->

# Апстрим-патч № 1: n8n-docs — MCP Server Trigger

Дата: 2026-11-02 · Волна: ROADMAP M3 «Первые патчи, отправленные в upstream-органы»
Итог: **патч подготовлен и вытолкнут в форк** (коммит 7f7270a, DCO); создание PR
заблокировано полномочиями токена — остался один шаг человека.

## Цель

Закон обмена (ADR-0001): органы не форкаем — отдаём патчи в upstream. До этого дня
организм только брал (реестр, конвейер); волна делает первый возврат.

## Разведка: карта занятости баг-очередей органов (2026-11-02)

Живая GitHub API разведка показала: первый же поиск «свободных» багов упирается в
очереди чужих PR — жанр выработан до нас. Правило «не становиться 11-м дубликатом»:

| Орган | Кандидат | Вердикт |
|---|---|---|
| microsoft/markitdown | #53 currency (метка «open for contribution») | **10+ открытых PR** с 2024 — очередь |
| microsoft/markitdown | whitespace/PDF | **63 PR** по жанру |
| browser-use/browser-use | #6209 SchemaOptimizer | репортёр сам несёт PR — территория занята |
| langflow-ai/langflow | #15869 cp1254 | 3 открытых PR (#15903 — ровно наш план фикса) |
| langflow-ai/langflow | #15859 дата-границы теста | PR #15860 |
| github/spec-kit | #4819 preset resolve | needs-triage; репортёр: «фикстура не исполнена независимо» — дефект не подтверждён |
| n8n-io/n8n-docs | MCP Server Trigger / Execute Command docs | **свободно: 0 открытых PR** к обеим страницам |

Выбор: n8n-docs — орган, для которого организм только что собрал конвейер (0.9.0);
MCP — наша компетенция (SPEC-0002); страницы рукотворные (`generated: true` нет).

## Дефект (верифицирован по исходнику узла)

Страница `docs/integrations/builtin/core-nodes/n8n-nodes-langchain.mcptrigger.md`
не знает о параметрах, которые уже в узле (`packages/@n8n/nodes-langchain/nodes/mcp/McpTrigger/McpTrigger.node.ts`,
`version: [1, 1.1, 2, 2.1]`):

- Authentication: отсутствует опция **n8n User Auth (OAuth2)** (v2+; в коде — между None и Bearer Auth);
- не задокументированы: **Require Workflow Execute Permission** (v2+, default true),
  **Trusted Source Name or ID** (v2+), **Include User in Output** (v2.1+, default true);
- параметр **Instructions** (все версии; текст, отдаваемый MCP-клиенту при подключении)
  не упомянут вовсе.

Проверки: 0 вхождений «OAuth2» / «Instructions» / «Include User» / «Trusted Source»
на странице (9307 байт); 0 открытых PR к файлу; формулировки патча взяты дословно
из описаний параметров в исходнике узла.

## Патч

- Форк: `rtynbirf/n8n-docs`, ветка `docs/mcp-trigger-parameters`, коммит **7f7270a** (DCO).
- Изменения: +1 опция аутентификации; +3 буллета параметров OAuth2; +секция Instructions
  между Path и Templates. Заголовки с якорями — по конвенции репозитория.
- Рядом с отчётом: `mcptrigger.patch` (полный diff), `pr-body.md` (готовое тело PR
  по шаблону n8n-docs: Summary / Related PRs / Preview / чек-лист).

## Блокер: один шаг человека

`POST /repos/n8n-io/n8n-docs/pulls` → **403 «Resource not accessible by personal
access token»**: fine-grained PAT не имеет права создавать PR в чужих публичных
репозиториях (push в собственный форк — есть, PR вверх по потоку — нет). Патч целиком
в форке; осталось одно:

- открыть compare-URL и вставить тело из `pr-body.md`:
  <https://github.com/n8n-io/n8n-docs/compare/main...rtynbirf:n8n-docs:docs/mcp-trigger-parameters>
- либо выдать токену право PR в публичных репозиториях (classic PAT с `public_repo`) —
  тогда волна дожмёт PR сама при следующем запуске.

После открытия PR репозиторий потребует **CLA** — подписывает человек, один раз.

## Урок волны: фантомный дефект, пойманный fail-closed

Первой ласточкой казался «сломанный markdown-линк» в Execute Command README
(«running ultiple commands](...)» — так его показал сырой fetch-дамп в терминал).
Скрипт патча упал на assert «broken link not found»; клон показал
«running [multiple commands](...)» — **ссылка цела**, файл не менялся неделями
(последний коммит — unrelated Databricks). Причина фантома: пара символов `[m`
съедена рендером терминального вывода. Правило на будущее: **дефект верифицируется
в клоне рабочей копии, не по fetch-дампам**; assert в скрипте — не бюрократия, а
иммунитет от ложного PR. Фантомная ветка удалена до пуша.

## Что дальше

- PR уходит одним шагом человека → ROADMAP-строка закрывается в 0.10.x.
- Канал «docs-vs-code дрейф» для органов, где у организма компетентный профиль
  (MCP, конвейеры, кровь) — переиспользуемый маршрут первых патчей.

## Аддендум (2026-11-02, вторая сессия)

- Попытка открыть PR через GitHub API токеном владельца: `POST /repos/n8n-io/n8n-docs/pulls` → **HTTP 403** «Resource not accessible by personal access token». Причина: токен fine-grained — GitHub не даёт write-операций (создание PR) в чужих публичных репозиториях, какими бы правами ни обладал владелец.
- Шаг по-прежнему за человеком: либо классический токен (`public_repo`), либо один клик по compare-URL:
  `https://github.com/n8n-io/n8n-docs/compare/main...rtynbirf:n8n-docs:docs/mcp-trigger-parameters?expand=1`
  — заголовок и тело PR готовы в `pr-body.md` (тело — после строки `---`).

## Аддендум (2026-11-02, третья сессия): PR ОТКРЫТ

- **n8n-io/n8n-docs#5689** — «docs(mcp server trigger): document OAuth2 auth option and missing parameters».
  1 коммит (`7f7270a`), +11/−0, `rtynbirf:docs/mcp-trigger-parameters` → `n8n-io:main`. PR открыл человек по
  compare-URL с готовым телом — compare-URL оказался самым коротким путём сквозь fine-grained-барьер.
- Реакция очереди — одна минута: лейблы `author:community`, `action:needs-review`, `scope:node-doc`;
  GitBook-превью опубликовано; запущен AI-ревьюер (cubic). Обязательные проверки: CLA Check (unsigned —
  до подписи), link-check, runner/vale.
- Осталось: ревью команды docs. CLA подписан человеком **2026-11-01T23:29:42Z** (cla-assistant,
  аккаунт rtynbirf) — редкий случай, когда «ошейник» надевается добровольно и один раз.
  Патч доехал до upstream по своей двери; DCO-дом оставлен в порядке, чужой дом — по его правилам.
- Цикл ревью замкнут: AI-ревьюер cubic вернул 4 замечания (P2 — версионная точность «трёх параметров»,
  P3 ×3 — жирный лейбл, ручной якорь нового заголовка, оксфордская запятая); все применены коммитом
  **894fa41** в ту же ветку PR через веб-редактор. Страница целиком перезаписана из клона рабочей
  копии — правило «дефект правится по файлу, а не по рендеру» сработало и здесь.
- Волна markitdown (#2438) продвинута максимально далеко от гейта токена: форк
  `rtynbirf/markitdown` создан API-вызовом (HTTP 202), патч наложен на свежий main чисто
  (`git am`, ветка `fix/html-docx-escape-pipes`, коммит de8d7bb, авторство и DCO сохранены).
  Гейт: fine-grained токен умеет читать и форкать, но Contents read-only — пуш в commons
  и в собственный форк → 403. Дожим (`scripts/finish_wave.sh`): пушcommons + пуш ветки +
  попытка PR + статус n8n; PR в microsoft после пуша — один клик compare-URL
  (fine-grained не умеет PR в чужих репо — это ограничение класса токена, не прав).
