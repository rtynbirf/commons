# Что изучено перед созданием репозитория (2026-11-01)

Мандат: «прежде чем создавать — изучи лучшие практики и структуры актуальных репозиториев». Фиксирую, что и откуда изучено, и что отсюда применено.

## 1. Официальные и общинные практики GitHub

Источники: docs.github.com «Best practices for repositories»; консолидированный ответ сообщества (GitHub Community, июнь 2026).

- Минимальный профессиональный комплект файлов: `README.md`, `LICENSE`, `.gitignore`, `CONTRIBUTING.md`; при росте — `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CHANGELOG.md`, `.env.example`, шаблоны issue/PR.
- Классификация репозитория: topics, описание, социальный превью.
- Бинарные артефакты и мусор в репо не хранить; артефакты — через релизы.

## 2. Тренд 2026: спеки — источник истины (SDD)

Источники: arXiv 2602.00180 «Spec-Driven Development: From Code to Contract in the Age of AI Coding Assistants» (30.01.2026); отраслевые гайды по SDD и ADR (2025–2026).

- Спеки — контракт для людей **и** агентов: «что будет сделано» фиксируется до реализации; уровни строгости: spec-first → spec-anchored → spec-as-source.
- **ADR** (Найгард, 2011; формат Статус/Контекст/Решение/Последствия) — журнал «почему»; SDD отвечает на WHAT+HOW, ADR — на WHY. Это не конкуренты, а пара.
- GitHub Spec Kit — референс-инструмент SDD (позиция 71 в снимке топ-100).

## 3. Живые структуры эталонов (GitHub API, contents/, 01.11.2026)

**github/spec-kit** (SDD-эталон, позиция 71):
`.editorconfig`, `.gitattributes`, `.pre-commit-config.yaml`, `.markdownlint-cli2.jsonc`, `AGENTS.md`, `CHANGELOG.md`, `CITATION.cff`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `DEVELOPMENT.md`, `SECURITY.md`, `SUPPORT.md`, README на 4 языках, `docs/`, `examples/`, `templates/`, `src/`, `tests/`, `.devcontainer`.

**openclaw/openclaw** (топ-агент, позиция 6):
`AGENTS.md`, `VISION.md`, `SECURITY.md`, `THIRD_PARTY_NOTICES.md`, `CHANGELOG/` + `CHANGELOG.md`, `CONTRIBUTING.md`, `.env.example`, `.pre-commit-config.yaml`, `.semgrepignore`, `skills/`, `docs/`, `examples/`, `extensions/`, `qa/`, `security/`, `tools/`, pnpm-монорепозиторий, `Dockerfile` + `docker-compose.yml`.

**anthropics/skills** (позиция 46):
`README.md`, `THIRD_PARTY_NOTICES.md`, `skills/`, `spec/`, `template/`, `.claude-plugin`, `.gitignore`.

## 4. Применённые решения (практика → файл)

| Практика 2026 | Применено здесь |
|---|---|
| AGENTS.md (spec-kit, openclaw) | `AGENTS.md` — правила для агентов как полноправных клеток |
| THIRD_PARTY_NOTICES.md (openclaw) | `THIRD_PARTY_NOTICES.md` — атрибуция органов и лицензии |
| SDD: спеки до кода | `specs/SPEC-0001..0003` — геном организма |
| ADR-журнал «почему» | `docs/adr/ADR-0001..0003` |
| Реестры как данные, не как проза | `organs/registry.yaml`, `synapse/mcp-manifest.yaml`, `blood/envelope.schema.json` (JSON Schema draft 2020-12) |
| Сообществский комплект | README (RU+EN), LICENSE, CONTRIBUTING, CoC, SECURITY, SUPPORT, CHANGELOG, `.env.example`, шаблон issue |
| Гигиена репо | `.editorconfig`, `.gitattributes`, pre-commit-совместимый Markdown, минимальный CI без сторонних экшенов |
| Минимальный CI | `.github/workflows/ci.yml`: валидация YAML/JSON + обязательный «Статус» в спеках |

## 5. Сознательные отличия от эталонов

- Нет кода ядра в 0.1.0: сначала геном (спеки), код приходит в M1 — это сам принцип SDD.
- Нет монорепо-обвязки: органы живут на upstream (ADR-0001), здесь только спеки, адаптеры и реестры.
- Двуязычность: русский — основной язык проекта; английский README — мост для внешних читателей (у spec-kit — обратная раскладка).
