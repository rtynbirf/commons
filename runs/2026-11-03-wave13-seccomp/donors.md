# Донорская книга волны №13 (трек B) — 2026-11-03

Мониторинг следующей очереди доноров живым API (токен №5, `GET /user` → 200).
Разведка REST'ом (gh CLI в песочнице отсутствует). Правила очереди — SPEC-0009 v0.1.2 п.9
(очередь проверяется в момент POST, `scripts/upstream_send.py`), правило «не становиться
11-м дубликатом», протокол-гейт волны №6 (issue-first у донора может быть невидим карте).

## Статусы донорских точек

| Точка | Статус | Детали |
|---|---|---|
| n8n-io/n8n-docs#5689 | OPEN, CI зелёный весь | CLA ✓, GitJob ✓, cubic-ревьюер ✓; reviewDecision = REVIEW_REQUIRED — ждёт человека; self-review доставлен 02.11 15:42Z |
| microsoft/markitdown#2808 | OPEN, `license/cla` ✓ | mergeable, саморевью доставлено; старшие очереди #2465/#2608 живы — активных действий не делать |
| microsoft/markitdown#2810 | OPEN, `license/cla` ✓ | mergeable, Fixes #2804; ноль ревью — ждать; обоснование nbformat<4 приложено |
| langchain-ai/langchain#41624 | ISSUE (не PR), OPEN | наш комментарий — единственный в треде (root cause + `add_special_tokens=False` + просьба об assignment); assignees пусты; наш PR #41632 закрыт ботом `require-issue-link` 02.11 13:26Z, коммит f0be70d жив в форке |
| microsoft/markitdown#2732 | OPEN, APPROVED (BichengWang, 21.10) | XLSX-жанр занят; без движения ~2 недели — смерджен не; резерв 5aeea96 ждёт смерти жанра |
| microsoft/markitdown#2766 | OPEN, COMMENTED-ревью 25.10 | второй XLSX-очередник — жанр занят дважды |
| shadcn-ui/ui#12567 | ISSUE (не PR), OPEN | upstream-issue ScrollArea/Safari; наш резерв a8d1b801 в форке `rtynbirf/ui`; PR из форка не отправлялся (queue-occupied) |
| shadcn-ui/ui#12568 | OPEN (PR конкурента), CI красен только Vercel | Vercel-деплой требует авторизации команды shadcn-pro — не дефект кода; Socket ×2 ✓, signed commits ✓; очередь занята |

Инвентаризация `search author:rtynbirf type:pr`: ровно 4 upstream-PR (3 открыты, 1 закрыт
ботом). Резервы подтверждены живьём: `rtynbirf/markitdown` — 3 ветки; `rtynbirf/langchain`
— `fix/issue-41631-tool-call-non-object-args` (5eaaba82); `rtynbirf/ui` —
`fix/scroll-area-viewport-tabindex` (a8d1b801); форк `rtynbirf/n8n-docs`.

## Дожимные действия (по триггерам, без пинга раньше тишины)

1. **langchain#41624** — главный дожимной: через 2–3 дня тишины вежливый follow-up в
   issue; после assignment — переоткрытие #41632 одним шагом (f0be70d жив в форке).
2. **langchain#41631 (резерв 5eaaba82)** — дожим только по issue-first протоколу:
   комментарий с подходом → assignment → PR (`--send`).
3. **5aeea96 (XLSX)** — дожим по триггеру смерти #2732/#2766; при интересе мейнтейнеров
   добавить просьбы ревьюера из #2766 (guard+тест).
4. **a8d1b801 (shadcn)** — дожим при смерти/забросе #12568; учесть конфликт-риск с
   открытым #11984 по тем же файлам при перебазировании.
5. **#5689/#2808/#2810** — merge за мейнтейнерами; при просьбах-правках закрывать быстро
   (патчи и тесты готовы).

## Следующая очередь доноров

- **Кандидат №1 — langchain (жанр #41631):** резерв 5eaaba82 верифицирован (core
  2453 passed), дожим после освоения issue-first протокола.
- **Кандидат №2 — повторный свип 48 ч по 10 `donate`-донорам** (правило волны №3:
  «через 3–5 дней или по триггеру»; прошлый свип 02.11 — стерилен только langchain,
  пора пересеять browser-use, ollama, spec-kit, llama.cpp, next.js, excalidraw, scrcpy,
  graphify, openclaw).
- **Кандидат №3 — протокол-гейт в донорские карты** (`organs/donation.yaml`): поле
  `protocol: none-observed | issue-first | cla-gate` — урок волны №6
  (require-issue-link сработал за 6 минут, карта его не видела).
