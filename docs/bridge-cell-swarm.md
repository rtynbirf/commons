# Мост cell-swarm ↔ COMMONS

Дата: 2026-11-05 · Стороны: дом COMMONS (v0.51.0, волна №32) и рой cell-swarm (0.1.0)

## Кто есть кто

- **Дом** — COMMONS: организм из лучших открытых проектов. Геном (спеки),
  синапсы (MCP), кровь (события с ценой), иммунитет (лицензии). Органы — на upstream.
- **Рой** — cell-swarm: клетки самого Человека (polymath-os, singulyar-llm,
  singulyar, cell65-host, rumu, voice-atlas-llm, global-video-platforms-registry),
  связанные геномом пинов. Рой — **пир дома**, не орган: он живет рядом,
  на том же хосте, и говорит с домом по грамматике согласия.

## Рукопожатие (ADR-0017)

```
рой ── peers/peer-manifest.json (name, transport, consents, provenance) ──→ дом
дом ── ConsentGrant (consent_id, peer, methods, granted_by=human, not_after) ──→ вердикт ДО факта
```

- Согласие дома — воля Человека (PID 1), живёт в доме.
- Согласие роя — consent/grants.json (зеркальный белый список: genome.read,
  genome.pins.read, organ.proposal.draft, blood.envelope.emit, blood.journal.append).
- Вердикты поимённые: granted / denied(peer_unknown | peer_silent |
  method_not_in_scope | revoked | expired). Повтор ключа обмена — записанный исход (A01).
- Живая проверка: `make cross-handshake COMMONS=<клон>` в рое импортирует
  `synapse/consent.py` дома и печатает вердикты обеих сторон (прогон 2026-11-05:
  genome.read → granted; memory.write → denied(method_not_in_scope)).

## Кровь (SPEC-0003)

События обмена несут цену всегда: `cost = {tokens_in, tokens_out, seconds[, attention]}`.
Тип — только из словаря дома (fail-closed, ADR-0014). Журнал роя append-only
с хэш-цепочкой `prev_id`/`prev_sha256`; каноническая форма
`json.dumps(ensure_ascii=False, sort_keys=True, separators=(",", ":"))` —
совпала с `canonical_sha256` дома байт-в-байт (cross-тест роя, 2026-11-05).

## Транспорты (ADR-0016)

Только локальные: `stdio` (скрипты роя) и `http-localhost`. Наружного шлюза нет
у роя по той же причине, что у дома: обмен живёт на хосте Человека.

## Тест отключения (G2, родной для обеих сторон)

- Без дома рой цел: `make verify && make blood-demo && make handshake` — офлайн.
- Без роя дом цел: дом не импортирует ничего из роя; связь — данные (YAML-голос,
  конверты), не код.
- Если одна из сторон «умирает» без другой — мост превращает сторону в паразита;
  это красная граница обеих архитектур.

## Будущее (не обещание, направление)

1. Клетки роя как органы дома — только по ритуалу ADR-0005: живая перепроверка
   лицензии (сейчас у 7 клеток лицензий нет — факт GitHub API 2026-11-05),
   живой пульс через синапсы, приёмка в CI.
2. Методы обмена расширяет Человек — ConsentGrant дома и grants.json роя правятся
   по-методно, «согласие на всё подряд» не заводится ни там, ни там.
