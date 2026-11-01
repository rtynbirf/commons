# Changelog

Формат основан на [Keep a Changelog](https://keepachangelog.com/); версии — SemVer.

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
