# Changelog

Формат основан на [Keep a Changelog](https://keepachangelog.com/); версии — SemVer.

## [0.2.0] — 2026-11-01

### Added

- **Исполнимое ядро** (ADR-0004): Python-пакет `commons-organism` в анатомических папках.
  - `blood/`: конверт с валидацией по JSON Schema (draft 2020-12) + append-only журнал; сумма цен по трейсу.
  - `synapse/`: шлюз — манифест как источник истины, veto необъявленного органа/инструмента, автоматическая замена по `substitutions`, динамическая загрузка адаптеров из манифеста (приёмка SPEC-0002: новый орган — правка манифеста, не кода).
  - `brainstem/`: канонический цикл PLAN→ACT→OBSERVE→REFLECT; бюджет G3 читается из крови; HALT; пустой план запрещён.
  - Адаптеры органов: ollama (HTTP, токены из ответа), llama.cpp (HTTP, запас), универсальный MCP-stdio (markitdown, browser-use и будущие органы).
- **26 приёмочных тестов** (`tests/`): G1 реконструкция сессии, G2 тест отключения, G3 бюджет, второй закон (нет вызовов мимо синапсов), veto, security.violation, валидность схемы крови.
- **Организм рисует себя сам**: `scripts/selfmap.py` → `docs/selfmap.md` (mermaid из живого реестра; AUTO-GENERATED).
- **Карточки органов M1**: `organs/{ollama,llama.cpp,markitdown,browser-use}/README.md` по шаблону карточки.
- Манифест синапсов 0.2.0: поле `adapter` у всех четырёх органов.
- CI: джоба `core` — pytest на Python 3.12 (setup-python запинен по SHA).

## [0.1.1] — 2026-11-01

### Added

- **Провенанс-якорь** `PROVENANCE.md`: декларация оригинальности («здесь нет ни байта чужого»), метод фиксации внешних фактов и верифицированная матрица лицензий 37 органов (живой GitHub API, 2026-11-01).
- **REUSE 3.3**: `REUSE.toml` (SPDX-аннотации), `LICENSES/Apache-2.0.txt`, джоб `reuse lint` в CI; экшены запинены по SHA, минимальные `permissions` (чеки Scorecard Pinned-Dependencies / Token-Permissions).
- `CITATION.cff` — цитируемость репозитория; `llms.txt` — карта для агент-клиентов.
- Вторая волна изучения: `docs/repo-structure-study.md` (структуры 10 эталонных репо, TOP-10 перенятых паттернов) и `docs/practices-checklist.md` (16 практик 2025–2026, MUST/SHOULD/LATER, статус применения).
- Инженерное исследование: `docs/research-plan.md` (31 проект, три приоритета), `docs/lenses.md` (шесть линз с весами и порогами), `docs/spikes.md` (S1–S5 с метриками и критериями выхода), `docs/glossary.md`.
- `docs/rating-verification.md` — живая сверка снимка топ-100 с API 2026-11-01: дельты звёзд и переезды владельцев (react, opencode, ComfyUI, prompts.chat, developer-roadmap). Идентичность органа — обмен, а не адрес.
- Шаблоны артефактов `docs/templates/`: SPEC, ADR, карточка органа (паттерны spec-kit / n8n / anthropics-skills).

### Changed

- Лицензии в `organs/registry.yaml`, `THIRD_PARTY_NOTICES.md`, `docs/organ-map.md` переведены из «предварительно» в верифицированные: superpowers → MIT, graphify → Apache-2.0, Awesome-Hacking → CC0-1.0, rea → MIT, x1xhlol → GPL-3.0, codex → Apache-2.0, opencode → MIT.
- `anthropics/skills` переведён из `dependency` в `reference`: формат навыков открыт, контент — по-навыковые условия Anthropic; свои навыки пишем сами по открытому формату.
- В реестр добавлен NousResearch/hermes-agent (MIT, 259k⭐, референс).
- CONTRIBUTING и AGENTS: DCO (`Signed-off-by`) обязателен; правила провенанса и пофайлового лицензирования.

## [0.1.0] — 2026-11-01

### Added

- Геном: SPEC-0001 (ствол мозга — канонический цикл), SPEC-0002 (синапсы — MCP-шлюз), SPEC-0003 (кровь — конверт событий).
- Реестр органов `organs/registry.yaml` (34 записи: режимы, системы, предварительные лицензии) и снимок рейтинга топ-100 `organs/top100-2026-10-26.yaml` (100 позиций, 26.10.2026).
- Манифест организма `docs/manifesto.md`: ЦЕЛОЕ > суммы частей, индивид как состояние связности, этимология ἰδιώτης/κοινός.
- Карта органов `docs/organ-map.md`; конспект изученных практик `docs/repo-practices-2026.md`.
- ADR-0001 (органы остаются на upstream), ADR-0002 (MCP как универсальный синапс), ADR-0003 (Apache-2.0).
- Синапсы: `synapse/mcp-manifest.yaml` — декларация органов как MCP-серверов + таблица замен (тест отключения).
- Кровь: `blood/envelope.schema.json` — JSON Schema (draft 2020-12) конверта событий.
- Сообществский комплект: README (RU/EN), AGENTS.md, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT, SUPPORT, CHANGELOG, THIRD_PARTY_NOTICES, шаблон issue «Заявка органа».
- CI: валидация YAML/JSON и обязательный «Статус» в спеках.
