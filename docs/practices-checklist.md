# Чек-лист практик open-source 2025–2026 и их статус здесь

Дата: 2026-11-02 · Волна 3 · Версия: 0.3.0

Консолидация актуальных практик (GitHub Community Standards, REUSE 3.3, OpenSSF Scorecard, ADR/MADR,
DCO, SemVer, docs-as-code, spec-driven development, MCP, SBOM) с вердиктом: MUST / SHOULD / LATER
для репо стадии blueprint и статус применения в COMMONS.

| # | Практика | Приоритет | Статус в COMMONS |
|---|---|---|---|
| 1 | Community health-файлы: README, LICENSE, CONTRIBUTING, CoC, SECURITY, шаблоны issues/PR | MUST | ✅ 0.1.0 + issue-шаблон «Заявка органа» |
| 2 | Мульти-сущностные health-файлы на уровне организации | SHOULD | отложено до второго репозитория организма |
| 3 | Лицензия с первого дня; явное соответствие «файл → лицензия» | MUST | ✅ Apache-2.0 (ADR-0003) |
| 4 | REUSE 3.3: SPDX-аннотации + `REUSE.toml` + `reuse lint` в CI | MUST | ✅ 0.1.1: `REUSE.toml`, `LICENSES/Apache-2.0.txt`, CI-джоб |
| 5 | SECURITY.md + приватный репортинг уязвимостей | MUST | ✅ 0.1.0 (Security Advisories) |
| 6 | CONTRIBUTING под документы (спеки через PR, стиль, глоссарий) | MUST | ✅ 0.1.0; 0.1.1 добавляет DCO и провенанс-правила |
| 7 | ADR-журнал `docs/adr/NNNN-*` (Статус/Контекст/Решение/Последствия) | MUST | ✅ 0.1.0 (ADR-0001..0003) + шаблон 0.1.1 |
| 8 | CITATION.cff — цитируемость репозитория | SHOULD | ✅ 0.1.1 |
| 9 | DCO (Signed-off-by) вместо CLA | SHOULD | ✅ 0.1.1: обязателен для всех коммитов; 0.10.0: распространено на исходящее донорство (SPEC-0007, ADR-0009) — гейт `commons-transplant`: кровь уходит в upstream только органам без CLA-ошейника (карты `organs/donation.yaml`, факты типирования с датой) |
| 10 | SemVer + теги + GitHub Releases как датированные якоря | SHOULD | ✅ релизы v0.1.0 и v0.1.1; CHANGELOG по Keep a Changelog |
| 11 | Docs-as-code: markdown в git, проверка текста в CI | MUST | ✅ 0.1.0 (валидация YAML/JSON + статус спек); markdownlint — LATER |
| 12 | Spec-driven development: поведение в спеках, исполняемых агентами | MUST | ✅ геном `specs/`, шаблоны в `docs/templates/`; S5 — приёмка |
| 13 | OpenSSF Scorecard (20 чеков: pinned deps, token-permissions, …) | SHOULD | ✅ 0.12.0: workflow `scorecard.yml` (action v2.4.2 по SHA, SARIF → Code Scanning), бейдж в README; до того — actions запинены по SHA, минимальные permissions |
| 14 | OpenSSF Best Practices Badge | LATER | после M1, когда появится исполняемый код |
| 15 | SBOM (SPDX/CycloneDX) и supply-chain гигиена | SHOULD (CI) / LATER (SBOM) | CI-гигиена ✅; 0.12.0: OSV-скан зависимостей (pip-audit, job `pathogens`) + dependabot (pip/actions); SBOM — при первом генерируемом артефакте |
| 16 | MCP как стандарт интеграции + `llms.txt` для агент-клиентов | SHOULD | ✅ MCP — ядро синапсов (ADR-0002); `llms.txt` 0.1.1 |

## Что изменилось против практик 2020-х

1. **Спека первична, код производен** — репозиторий blueprint-стадии полноценен, а не «заглушка».
2. **Агенты — вторая аудитория репо**: AGENTS.md, llms.txt, машинно-читаемые лицензии (SPDX/REUSE.toml).
3. **Supply chain по умолчанию**: pinning actions по SHA, минимальные `permissions`, SBOM как норма, а не паранойя.
4. **Лицензирование стало пофайловым и проверяемым** (REUSE 3.3 вытеснил «LICENSE в корне и надеемся»).
5. **Доверие = проверяемые сигналы**: community profile, Scorecard, REUSE, DCO — вместо деклараций.

## Источники волны 2

- GitHub Docs: community profiles / citation files / default health files (docs.github.com).
- REUSE 3.3: reuse.software/spec-3.3 (REUSE.toml, SPDX-поля).
- OpenSSF Scorecard: список чеков (github.com/ossf/scorecard, docs/checks.md), scorecard.dev.
- ADR: adr.github.io (MADR-традиция).
- DCO 1.1: developercertificate.org.
- SemVer: semver.org. Docs-as-code: writethedocs.org/guide/docs-as-code.
- SDD: github/spec-kit. MCP: modelcontextprotocol.io. SBOM: spdx.dev, cyclonedx.org (ECMA-424).

Живое изучение структур десяти эталонов: [repo-structure-study.md](repo-structure-study.md).
