# Run: собственный CI-пожар и ревизия доски (2026-11-02, токен №5)

## Триггер

«поехали» + токен №5 (classic, тяжёлые скоупы: repo, workflow, admin:\*).
Обход уведомлений сразу показал: красный CI не только в апстриме, но и в
СОБСТВЕННЫХ репо — это работа, не требующая людей, и берётся она первой.

## domovoy-tweaker: main красный → починен без людей

- CI `Lint + Test (windows-latest)`: 40/41, детерминированно падает
  `apply file.attribute adds the attribute; undo restores the exact previous set`
  с `IOException: Could not find item …\Temp\domovoy-file-<guid>.txt`
  (ранны 41366091855 и 41419841550 на main, оба).
- Корень: провайдер PowerShell прячет файлы с атрибутом Hidden от
  `Get-Item` без `-Force`. apply ставил Hidden → идущая следом
  верификация (`file.attributes` в `Test-DomovoyEffect`) читала атрибуты
  обычным `Get-Item` и падала; undo скрытый файл молча пропускал.
  Баг продукта, не флейк: `file.attribute` не мог применить Hidden ни разу.
- Фикс: PR rtynbirf/domovoy-tweaker#1 (45a4947 + 4e7927c), squash →
  46def9e, main снова зелёный (ран 41423913211: success). PR #2 —
  changelog (Keep a Changelog, `[Unreleased]/Fixed`) → смержен.
- Итерация честно: в 45a4947 поставил `-Force` и на `Test-Path` —
  у него такого параметра нет (ParameterBindingException в первом CI-ране
  PR); 4e7927c убрал. `Test-Path` скрытые файлы видит, слеп только
  `Get-Item`. CI поймал за один цикл.
- Проверка канала: ошибка вылетает из `Invoke-DomovoyFeature` на строке
  apply (тест не доходил до assert'а — иначе был бы mismatch, а не
  IOException), тайминги 10–17 мс сходятся, оба рана main идентичны.

## commons: уведомления оказались шумом

Раны 00:00:31–36Z «ci.yml failed» — ветки dependabot ДО merge; PR #1–#4
все смержены в 00:04Z, main зелёный. Действий не требуется.

## Ревизия доски (проверено API, не по памяти)

- markitdown#2804 — ЧУЖОЙ ISSUE (CHX606, «Ordinary JSON is silently
  discarded…»), не PR. Запись f7b38fe «#2804 верифицирован» означает
  верификацию issue; PR волны-2 — соседний номер.
- markitdown#2810 — наш PR волны-2 «fix(ipynb): require notebook
  structure, not marker substrings» (Fixes #2804), head
  aaf26e7@rtynbirf/markitdown, открыт 09:19:03Z токеном №5,
  license/cla: success, mergeable_state=blocked, комментариев нет.
- Доска целиком: markitdown #2465, #2608, #2808 (pipes), #2810 (ipynb),
  n8n-docs#5689 (mcp trigger docs) — все открыты, ни одного вердикта
  мейнтейнеров; у наших PR CLA зелёный везде.
- Конвергенция: урок «очередь проверяется в момент POST» уже реализован
  соседом (10c26d9, `scripts/upstream_send.py`, fail-closed, 11 приёмок,
  живая проба: жанр «escape pipes» отвергается как занятый). Локальный
  черновик `scripts/wave_post_v3.py` перекрыт им; канонический механизм —
  в репо, пользуюсь им.

## Токен №5

Скоупы тяжёлые (repo, workflow, admin:\*, delete_repo). Использован
только на: чтение API, ветки+PR+merge в СОБСТВЕННОМ domovoy-tweaker,
push отчёта. Кнопки merge в microsoft/markitdown и n8n-io/n8n-docs —
не мои: скоупы не равны правам коллаборатора. ЧЕЛОВЕК=PID=1:
симулировать merge за мейнтейнеров — тот же грех, что #2467.

## Уроки

1. Обход уведомлений — источник реальной работы без людей: красный CI
   в собственных репо чинится сразу, а не «ждёт ревью».
2. PowerShell: `Get-Item` слеп к Hidden без `-Force`; у `Test-Path`
   параметра `-Force` нет вообще. Сигнатуры API проверять до пуша.
3. Записи о каналах верифицировать API до попадания в отчёт: «#2804»
   оказался issue, «#2810» — PR. Проверка стоит один GET.
