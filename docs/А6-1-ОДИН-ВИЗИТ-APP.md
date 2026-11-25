# А6-1 · GitHub App «кровь-геном» (krov-genom) + PEM · один визит владельца

Статус: ГОТОВ К ОДНОМУ КЛИКУ · собран 2026-11-25 волной А6 · манифест 342 байта, sha256 `4c19b7e1acc8603687ec99c8648721468493e0482a3b7fe70c0db663b13dddd0` · state `3302360a2fb80fc77718ac5e`

## 1. Физика API (доказано кодами, не памятью)

- Создание GitHub App через REST/GraphQL **не существует**: OpenAPI-схема GitHub (github/rest-api-description, operationId `apps/create-from-manifest`) знает ровно одну дверь — `POST /app-manifests/{code}/conversions`. Проба ложным кодом → HTTP 404 с `documentation_url` на якорь `#create-a-github-app-from-a-manifest`: эндпоинт жив, 404 = «такого кода нет».
- Мутации GraphQL профиля/App-создания отсутствуют (интроспекция: 269 полей Mutation, pin-класс — только `pinEnvironment/pinIssue/pinIssueComment`).
- Вывод: манифест-флоу. Владелец открывает предзаполненную ссылку → нажимает **Create GitHub App** → GitHub редиректит `?code=…&state=…` → конверсию делает агент. Это минимальная физика: одна кнопка.

## 2. ОДИН КЛИК (ссылка)

https://github.com/settings/apps/new?state=3302360a2fb80fc77718ac5e&manifest=eyJuYW1lIjoia3Jvdi1nZW5vbSIsInVybCI6Imh0dHBzOi8vZ2l0aHViLmNvbS9ydHluYmlyZi9jb21tb25zIiwiaG9va19hdHRyaWJ1dGVzIjp7InVybCI6Imh0dHBzOi8vd2ViaG9vay5zaXRlLzUyMzZlMTkwLTQ0YWEtNDM1Yy05M2I1LWUyYzc2OTRlMWVmOCIsImFjdGl2ZSI6ZmFsc2V9LCJyZWRpcmVjdF91cmwiOiJodHRwczovL3dlYmhvb2suc2l0ZS81MjM2ZTE5MC00NGFhLTQzNWMtOTNiNS1lMmM3Njk0ZTFlZjgiLCJwdWJsaWMiOmZhbHNlLCJkZWZhdWx0X3Blcm1pc3Npb25zIjp7ImNvbnRlbnRzIjoicmVhZCIsIm1ldGFkYXRhIjoicmVhZCJ9LCJkZWZhdWx0X2V2ZW50cyI6WyJwdXNoIl19

Манифест: name `krov-genom` (свободно: GET /apps/krov-genom → 404), homepage — commons, webhook `active: false` (доставки не шлют), права только кровь: `contents: read` + `metadata: read`, событие `push`, `public: false`.

Что произойдёт после клика:

1. GitHub создаст App и перебросит браузер на каптуру `webhook.site/5236e190-…` с `?code=…&state=…`;
2. агент заберёт код с каптуры, сверит `state` и сконвертирует его через `POST /app-manifests/{code}/conversions`;
3. ответ принесёт `id`, `slug`, `client_id`, `webhook_secret` и **`pem`** — вся связка «кровь-геном» рождена одной кнопкой;
4. закон дома: pem и секреты живут только в чате/env, в файлы и git не пишутся; в отчётах — только отпечаток `sha256(pem)[:12]`; свою копию pem владелец всегда может скачать на странице созданного App.

## 3. Фолбэк (если каптура молчит)

В адресной строке после клика виден `?code=…` — скопировать одну строку и вставить в чат. Конверсия та же, state сверяется тем же образом.

## 4. Установка App на репозитории

После создания GitHub предложит «Install» — тот же визит, ещё один клик: https://github.com/apps/krov-genom/installations/new (выбрать All repositories). Живая проба крови после установки: JWT (RS256, pem из env) → `POST /app/installations/{id}/access_tokens` → GET contents любого репо флота.

## 5. Безопасность

- манифест без секретов — ссылка безопасна для репо;
- каптура одноразовая: код сгорает конверсией (TTL ~10 минут);
- `state` сверяется при конверсии;
- pem/webhook_secret/client_secret никогда не попадают в git (закон дома).

## 6. Хронология попыток (честно)

- 2026-11-25: `POST /apps/manifest/conversions` (единственное число) → HTTP 404 generic; OpenAPI поправил путь на `app-manifests` (множественное) — подтверждено `operationId apps/create-from-manifest`.
- Имена `krov-genom`, `krovgenom`, `krov-genom-app` свободны (GET → 404).
