# Карта органов COMMONS v0.1.1

Дата: 2026-11-01 · Ранг и звёзды — снимок 26.10.2026 (`organs/top100-2026-10-26.yaml`) · Лицензии верифицированы живым GitHub API 2026-11-01 ([PROVENANCE.md](../PROVENANCE.md)); перед подключением перепроверяются по файлу LICENSE upstream.

Режимы: **зависимость** — работает в теле (только permissive); **адаптер** — наш тонкий код вокруг органа; **внешний узел** — вне тела (AGPL/fair-code/проприетарные); **референс** — только изучение; **субстрат** — среда, не модифицируем; **обучение** — репродукция клеток команды.

## Ядро (семь систем)

| Система | Орган | Ранг | Режим | Лицензия (предв.) |
|---|---|---|---|---|
| Геном | github/spec-kit | 71 | зависимость | MIT |
| Геном | anthropics/skills | 46 | референс (открытый формат) | по-навыковые (ToU Anthropic) |
| Геном | obra/superpowers | 13 | референс | MIT |
| Ствол мозга | собственный канонический цикл (SPEC-0001) | — | свой код | — |
| Ствол мозга | референсы: openclaw (6), claude-code (61), opencode (25), codex (85) | — | референс | смешанные |
| Синапсы | MCP-шлюз (SPEC-0002) | — | свой код | — |
| Кровь | конверт событий (SPEC-0003) | — | свой код | — |
| Метаболизм | ollama/ollama | 43 | зависимость | MIT |
| Метаболизм | ggml-org/llama.cpp | 83 | зависимость (запас ollama) | MIT |
| Метаболизм | huggingface/transformers | 52 | зависимость | Apache-2.0 |
| Память | Graphify-Labs/graphify | 80 | кандидат (M2) | Apache-2.0 |
| Память | векторная БД | — | выбор в Этапе 0 | — |
| Иммунитет | Hack-with-Github/Awesome-Hacking (знания) | 91 | референс | CC0-1.0 |
| Иммунитет | лицензионный барьер в CI | — | политика | — |

## Периферия

| Система | Орган | Ранг | Режим | Лицензия (предв.) |
|---|---|---|---|---|
| Сенсорика | microsoft/markitdown | 37 | зависимость | MIT |
| Сенсорика | firecrawl/firecrawl | 34 | внешний узел (hosted API) | AGPL-3.0 |
| Сенсорика | x1xhlol/system-prompts-and-models-of-ai-tools | 66 | референс-корпус | GPL-3.0 |
| Эффекторы | openclaw/openclaw | 6 | зависимость (M2) | MIT |
| Эффекторы | browser-use/browser-use | 98 | зависимость (M1) | MIT |
| Эффекторы | morluto/rea | 7 | адаптер (опционально) | MIT |
| Эффекторы | NousResearch/hermes-agent | — | референс | MIT |
| Нервные альтернативы | langchain-ai/langchain | 64 | зависимость (M2) | MIT |
| Нервные альтернативы | langgenius/dify | 56 | адаптер, условная | Apache-2.0 с условиями |
| Нервные альтернативы | langflow-ai/langflow | 59 | референс | MIT |
| Нервные альтернативы | n8n-io/n8n | 28 | внешний узел | fair-code |
| Железы | Comfy-Org/ComfyUI | 68 | отдельный процесс | GPL-3.0 |
| Железы | AUTOMATIC1111/stable-diffusion-webui | 53 | внешний узел | AGPL-3.0 |
| Кожа | react/react | 22 | зависимость | MIT |
| Кожа | shadcn-ui/ui | 90 | зависимость | MIT |
| Кожа | vercel/next.js | 67 | зависимость | MIT |
| Самоописание | excalidraw/excalidraw | 82 | зависимость (M2) | MIT |
| Удалённость | Genymobile/scrcpy | 62 | адаптер | Apache-2.0 |
| Удалённость | rustdesk/rustdesk | 88 | внешний узел | AGPL-3.0 |
| Субстрат | torvalds/linux | 20 | субстрат | GPL-2.0 |
| Субстрат | kubernetes/kubernetes | 87 | субстрат | Apache-2.0 |
| Субстрат | nodejs/node | 94 | субстрат | MIT |
| Субстрат | golang/go · rust-lang/rust | 77 · 96 | субстрат | BSD-3 · MIT/Apache |
| Репродукция | codecrafters-io/build-your-own-x | 1 | обучение | NOASSERTION (только чтение) |
| Репродукция | donnemartin/system-design-primer | 8 | обучение | NOASSERTION (только чтение) |
| Репродукция | ossu/computer-science | 27 | обучение | MIT |

## Вне организма

- `anthropics/claude-code` (61), `openai/codex` (85) — внешние инструменты разработчика, не части тела.
- `2dust/v2rayN` (99), `clash-verge-rev/clash-verge-rev` (60) — сетевые клиенты среды, не органы.

## Потоки обмена (упрощённо)

```
                 ┌─────────────── ГЕНОМ (spec-kit · skills · superpowers) ───────────────┐
                 │                                                                        │
 СЕНСОРИКА ──► КРОВЬ (envelope, cost) ──► СТВОЛ МОЗГА (цикл) ──► СИНАПСЫ (MCP) ──► ЭФФЕКТОРЫ
 firecrawl ▲                    ▲                ▲                    │             openclaw
 markitdown │                    │                │                    ▼             browser-use
            │                 ПАМЯТЬ ────────────┘            МЕТАБОЛИЗМ (ollama ⇄ llama.cpp)
            │              graphify + вектора                              │
            └──────────────────────────────────────────────────────────────┘
                        ИММУНИТЕТ: лицензии + supply chain (контур вокруг всего)
```

Каждая стрелка — событие в крови с ценой. Орган, не участвующий ни в одной стрелке, — кандидат на вывод (закон обмена).
