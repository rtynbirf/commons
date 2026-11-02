# BASELINE — сращение пакета «Human Membrane» v0.1.0 с COMMONS

Этап 0 дорожной карты пакета (`docs/05_ROADMAP_RU.md`): зафиксировать фактическое
тело репозитория и отметить каждую точку пакета статусом. Статусы — по конституции
пакета (`docs/01_PRODUCT_CONSTITUTION_RU.md`): `USER_DESIGN`, `REPO_FACT`,
`REFERENCE_DESIGN`, `TESTED`, `UNKNOWN`. Повышение по аналогии или самоотчёту
запрещено.

## 0. Реквизит

| Факт | Значение |
|---|---|
| Пакет | `COMMONS_Human_Membrane_Implementation_Package_v0.1.0.zip`, дата 2026-11-02 |
| Целостность пакета | `sha256sum -c MANIFEST.sha256` — все файлы OK, TESTED (только архив) |
| Тело репо | commit `7f048ec` (v0.32.0, волна №13 такт 2) |
| Базовый прогон без изменений (до каталога прогона) | `python3 -m pytest -q`: **519 passed, 14.82 s** |
| Прогон после добавления каталога прогона | **525 passed, 15.19 s** — гематология (`tests/test_hematology.py`) параметризована по `runs/*/blood.jsonl`, новый журнал добавил кейсы |
| Дата прогона | 2026-11-03 |

STATUS_LEDGER пакета помечал `REPO_FACT: UNKNOWN` («нет рабочей копии репозитория»).
Этот документ закрывает тот пробел: рабочая копия есть, точки сверены по живым файлам.

## 1. Карта точек пакета → тело репо

| # | Точка пакета | Тело репо (REPO_FACT) | Статус | Доказательство |
|---|---|---|---|---|
| 1 | Blood store (append-only) | `blood/journal.py` `Journal` — append-only, цепочка `prev_id`, `verify` гэпов | REPO_FACT | `tests/test_blood.py`, SPEC-0003 |
| 2 | Схема события | `blood/envelope.schema.json` — поля: `id, ts, type, source, organ, trace_id, payload, cost, prev_id` | REPO_FACT | валидация до записи, отказной режим |
| 3 | Resume из крови | `blood/resume.py` — реконструкция сессии | REPO_FACT | `tests/test_blood_resume.py` |
| 4 | Dedupe / идемпотентный append | повторный `event_id` не даёт второго эффекта (пакет A01) | UNKNOWN | в схеме нет `idempotency_key`; поведение append на дубль не зафиксировано приёмкой |
| 5 | Dispatcher (cursor/ack/retry/dead-letter) | `brainstem/loop.py` — цикл и бюджет; cursor/ack/dead-letter **отсутствуют** | NOT_BUILT | grep по loop.py пуст |
| 6 | Scheduler / приоритеты / бюджет ресурса | `brainstem/budget.py` — декларативные лимиты метаболизма из манифеста | REPO_FACT (≠ attention-бюджет пакета) | SPEC-0001 G3 |
| 7 | Полномочия / permissions | `synapse/authority.py` — скоупы процессов (spawn/socket/files), дети, seccomp | REPO_FACT (≠ approval человека) | `tests/test_authority*.py`, SPEC-0002 |
| 8 | Immune — входная безопасность | `immune/barrier.py` + гейт | REPO_FACT | `tests/test_immune.py`, `tests/test_immune_gate.py` |
| 9 | Swarm — обмен знаниями (consent, manifest, provenance) | `immune/donation.py` — донорство upstream-PR | ЧАСТИЧНО | consent-обмен пакетами НЕ построен (A21/A22 — UNKNOWN) |
| 10 | Память (движок) | `memory/` — engine, graph, vectors, replay | REPO_FACT | `tests/test_memory_*.py` |
| 11 | Память-файлы (commons-memory/, экспорт/импорт/diff) | отсутствует | NOT_BUILT | grep пуст (A12/A13) |
| 12 | Дневник человека | отсутствует | NOT_BUILT | grep diary пуст (A04/A05) |
| 13 | Undo / compensator | отсутствует | NOT_BUILT | grep undo пуст (A06–A09) |
| 14 | Attention budget (внимание человека) | отсутствует | NOT_BUILT | grep attention пуст (A14) |
| 15 | Forget (контролируемое удаление) | отсутствует | NOT_BUILT | grep forget пуст (A11) |
| 16 | Approval перед необратимым | отсутствует; ближайшее родство — `authority.py`, но это полномочия процессов | NOT_BUILT (A15 — UNKNOWN) | — |
| 17 | MCP gateway | `synapse/gateway.py` + `mcp-manifest.yaml` | REPO_FACT | `tests/test_synapse.py` |
| 18 | Органы как функции организма (10 органов пакета) | `organs/registry.yaml` — реестр **внешних зависимостей**, не функции | СЛОВАРНЫЙ КОНФЛИКТ | см. §3 |
| 19 | UI / доступность (screen reader, keyboard) | отсутствует | NOT_BUILT | — |
| 20 | CI | `.github/` — гигиена, гематология, донорские гейты | REPO_FACT | волна №5: 10/10 зелёных |
| 21 | Кровь как журнал прогонов | `runs/**/blood.jsonl`, гематология на каждой волне | REPO_FACT | 32 конверта волны №13 без гэпов |

## 2. Схема крови: тело репо ↔ контракт пакета

`REFERENCE_DESIGN` пакета — `schemas/blood-event.schema.json`. Сверка по полям:

| Поле пакета | Поле репо | Вердикт |
|---|---|---|
| `event_id` | `id` | Эквивалент — транслируется адаптером |
| `event_name` | `type` | Эквивалент |
| `schema_version` | — | **Добавить** (совместимость: файл без цепочки = v0.4, `prev_id` = v0.5) |
| `occurred_at` (nullable) | — | **Добавить** nullable |
| `observed_at`, `stored_at` | `ts` | `ts` покрывает момент записи; развести при добавлении |
| `trace_id` | `trace_id` | Эквивалент |
| `correlation_id` | — | **Добавить** |
| `causation_id` | `prev_id` | Родство по смыслу; `prev_id` — цепочка файла, causation — причина события; развести при добавлении |
| `sequence` | — | **Добавить** или выводить из порядка чтения |
| `payload` | `payload` | Эквивалент |
| `cost` {tokens, duration_ms, money, attention} | `cost` | Есть; детализация сверяется в PR-1 по `envelope.Cost` |
| `trust` (unverified/verified/derived/unknown) | — | **Добавить** |
| `privacy` (public/internal/personal/sensitive) | — | **Добавить** |
| `retention` (nullable) | — | **Добавить** nullable |

Схема пакета — `additionalProperties: false`: старые конверты репо без расширений
в неё не встанут. Вывод: не ломать `envelope.schema.json`, а наращивать поля
добавлением + тонкий транслятор package↔repo (пакет прямо требует тонкий adapter,
не переписывание органов).

## 3. Словарь: три несоответствия, которые надо назвать до PR-1

1. **«Орган».** У пакета орган = функция организма (endocrine, limbic, olfactory…).
   В репо `organs/registry.yaml` — реестр внешних зависимостей (ollama, markitdown…).
   Пакетные десять органов — это СИСТЕМЫ репо (selfmap, brainstem, immune…), а не
   позиции реестра. Предложение: отобразить десять органов пакета на системы в
   `docs/selfmap.md`, реестр не трогать. Решение оформить ADR в PR-1.
2. **«Бюджет».** `brainstem/budget.py` — лимиты метаболизма органов. Attention-бюджет
   пакета — счётчик прерываний ЧЕЛОВЕКА. Разные сущности, разные файлы.
3. **«Полномочия».** `synapse/authority.py` — полномочия процессов (что детёнышу можно
   spawn/connect/писать). Approval пакета — разрешение ЧЕЛОВЕКА перед необратимым.
   Родственная дисциплина (запрет по умолчанию), но разные контуры; approval строится
   поверх, а не внутри.

## 4. Гипотезы пакета — НЕ переносить как факты

80/15/5, торможение >85%, «спешит/отклоняет» лимбика, анти-sycophancy баллы —
`USER_DESIGN`/гипотезы. Путь в репо один: спайк → замер → ADR (как S6 для памяти).
Критерии не менять задним числом.

## 5. Порядок работ (INTEGRATION_GUIDE пакета, уточнён под тело репо)

| Шаг | Содержание | Приёмки пакета |
|---|---|---|
| PR-1 | Blood adapter: добавить `schema_version, occurred_at, correlation_id, sequence, trust, privacy, retention`; транслятор package↔repo; совместимость v0.4/v0.5 файлов | A01, A02, A17 |
| PR-2 | Дневник-проекция read-only из живой крови; экспорт Markdown/JSONL | A03, A04, A05, A10 |
| PR-3 | Action descriptor + ОДИН реальный локальный compensator (выбрать после аудита эффекторов, не придумывать) | A06, A07, A08, A09 |
| PR-4 | Память-файлы: экспорт/импорт/diff/forget с обходом индексов и кэшей | A11, A12, A13 |
| PR-5 | Attention + approval поверх `authority.py` | A14, A15, A23 |
| PR-6+ | Органы по одному: immune уже есть (A18), conscience (A19), creative-sandbox (A20), swarm-consent (A21, A22), redelivery/backpressure (A24, A25) | по ходу |

## 6. Вердикт Этапа 0

- Точек карты: **21**. REPO_FACT: **10**. NOT_BUILT: **8**. ЧАСТИЧНО: **1**.
  СЛОВАРНЫЙ КОНФЛИКТ: **1**. UNKNOWN внутри фактов (dedupe): **1**.
- Пакет скачан ≠ пакет интегрирован. Ни один статус не повышен самоотчётом.
- Следующий шаг: PR-1 (Blood adapter) — тонкий слой, старые файлы крови остаются валидными.
