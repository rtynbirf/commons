# Структуры десяти эталонных репозиториев — что перенято

Дата: 2026-11-01 · Волна 2 · Версия: 0.1.1

Вторая волна изучения перед бетонировкой: разобраны верхнеуровневые структуры десяти живых
репозиториев (корень, `.github`, docs, приёмы организации). Первая волна — в
[repo-practices-2026.md](repo-practices-2026.md).

## Сводка по репозиториям

| Репозиторий | Корень (существенное) | Community-файлы | Ключевой приём |
|---|---|---|---|
| github/spec-kit | templates/, docs/, scripts/, .specify/memory/ | полный стек + CITATION.cff, SUPPORT, issue-формы submission | живая «конституция» + каталог шаблонов артефактов |
| anthropics/skills | skills/, spec/, template/ | минимум; лицензии внутри каждого навыка | каждый артефакт = папка с манифестом (SKILL.md) + спека формата + болванка |
| obra/superpowers | skills/, docs/ (датированные design-доки) | CoC, PR-шаблон | один контент → манифесты для 10+ агентных платформ |
| ollama/ollama | Go-монорепо, docs/ (Mintlify + OpenAPI) | CONTRIBUTING, SECURITY | AGENTS.md + CLAUDE.md как входы агентов |
| ggml-org/llama.cpp | src/, docs/, skills/, licenses/ | CODEOWNERS, PR-шаблон | навыки для агентов прямо в продуктовом репо; каталог сторонних лицензий |
| langchain-ai/langchain | libs/ (монорепо), openwiki/ | CITATION.cff, CODEOWNERS | агент-поддерживаемая вики с манифестом страниц |
| langgenius/dify | api/, web/, skills/, docs/ (17 локалей) | CoC, CODEOWNERS, DISCUSSION_TEMPLATE | i18n-доки; skills для агентов-сопровождающих |
| browser-use/browser-use | browser_use/, skills/, examples/ | CONTRIBUTING/SECURITY в .github | машинно-читаемые манифесты интеграции (server.json) |
| excalidraw/excalidraw | packages/, dev-docs/ (Docusaurus) | CONTRIBUTING, copilot-instructions.md | отдельный док-сайт для контрибьюторов |
| n8n-io/n8n | packages/, docs/adr/, security/, OWNERS | CoC, CLA, OWNERS | docs/adr/ с шаблоном; OWNERS как машинная governance |

## TOP-10 паттернов, перенятых здесь

1. **Артефакт = папка с манифестом** (anthropics/skills, llama.cpp, browser-use) → карточки органов
   через шаблон `docs/templates/ORGAN-TEMPLATE.md`.
2. **Спека формата + болванка рядом** (anthropics/skills) → `docs/templates/` содержит и шаблон, и правило.
3. **Живая конституция как первичный артефакт** (spec-kit `.specify/memory/constitution.md`) → аксиомы
   и три закона живут в [manifesto.md](manifesto.md), инварианты агентов — в [AGENTS.md](../AGENTS.md).
4. **Каталог шаблонов всех типов артефактов** (spec-kit templates/) → SPEC-TEMPLATE, ADR-TEMPLATE, ORGAN-TEMPLATE.
5. **ADR-каталог с шаблоном** (n8n docs/adr/) → `docs/adr/` + шаблон.
6. **Один источник → множество манифестов** (superpowers) → реестры как данные (YAML/JSON), проза не дублирует данные.
7. **Эталонный community-стек** (spec-kit) → README RU+EN, CONTRIBUTING, CoC, SECURITY, SUPPORT, CHANGELOG,
   CITATION.cff, шаблоны issues.
8. **Машинная governance** (n8n OWNERS, CODEOWNERS) → правила как проверяемые файлы: `REUSE.toml`,
   `REPO-STRUCTURE` чек в CI, а не вики-страницы.
9. **Контрибуция артефактов через структурированные формы** (spec-kit submission-формы) → issue-шаблон «Заявка органа».
10. **Agent-entry в корне** (AGENTS.md — 9 из 10 репо) → [AGENTS.md](../AGENTS.md) + [llms.txt](../llms.txt).

## Сознательные отличия

- **REUSE 3.3 (SPDX) поверх всех**: ни один из десяти эталонов не ведёт пофайловое лицензирование
  через REUSE.toml — для организма-коммонса это иммунный приоритет (см. [practices-checklist.md](practices-checklist.md)).
- **PROVENANCE.md с верифицированной матрицей** — вместо привычного «THIRD_PARTY_NOTICES по памяти»:
  у нас таблица датирована живой проверкой API.
- Плоский markdown вместо док-сайта: сайт — в M2/M3, когда появятся генерируемые страницы (карта органов из реестра).
