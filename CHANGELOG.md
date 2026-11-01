# Changelog

Формат основан на [Keep a Changelog](https://keepachangelog.com/); версии — SemVer.

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
