# Сторонние компоненты (органы)

COMMONS **не копирует** код органов: органы остаются в своих upstream-репозиториях, здесь живут только спеки, адаптеры и реестры.

Лицензии в таблице — **верифицированные**: аутентифицированный GitHub API `GET /repos/{owner}/{repo}`, 2026-11-01. Полная матрица со звёздами и расшифровкой всех `NOASSERTION` — в [`PROVENANCE.md`](PROVENANCE.md). Перед фактическим подключением органа лицензия дополнительно перепроверяется по файлу `LICENSE` в upstream (закон иммунитета, ADR-0001).

| Орган | Upstream | Лицензия (верифицировано 2026-11-01) | Режим |
|---|---|---|---|
| openclaw | openclaw/openclaw | MIT | эффектор / референс ствола мозга |
| anthropics/claude-code | anthropics/claude-code | NOASSERTION — проприетарная | внешний инструмент |
| anomalyco/opencode | anomalyco/opencode | MIT | референс |
| openai/codex | openai/codex | Apache-2.0 | внешний инструмент |
| NousResearch/hermes-agent | NousResearch/hermes-agent | MIT | референс |
| browser-use | browser-use/browser-use | MIT | зависимость |
| morluto/rea | morluto/rea | MIT | опциональный орган |
| spec-kit | github/spec-kit | MIT | геном |
| anthropics/skills | anthropics/skills | по-навыковые (ToU Anthropic) | референс: формат открыт, контент не копируем |
| superpowers | obra/superpowers | MIT | референс |
| langchain | langchain-ai/langchain | MIT | зависимость |
| dify | langgenius/dify | Apache-2.0 с дополнительными условиями | адаптер, условная |
| langflow | langflow-ai/langflow | MIT | референс |
| n8n | n8n-io/n8n | Sustainable Use License (fair-code) | внешний узел |
| ollama | ollama/ollama | MIT | зависимость |
| llama.cpp | ggml-org/llama.cpp | MIT | зависимость |
| transformers | huggingface/transformers | Apache-2.0 | зависимость |
| graphify | Graphify-Labs/graphify | Apache-2.0 | кандидат (память) |
| firecrawl | firecrawl/firecrawl | AGPL-3.0 | hosted API / изолированный узел |
| markitdown | microsoft/markitdown | MIT | зависимость |
| system-prompts-and-models-of-ai-tools | x1xhlol/system-prompts-and-models-of-ai-tools | GPL-3.0 | референс-корпус: читаем, не копируем |
| ComfyUI | Comfy-Org/ComfyUI | GPL-3.0 | отдельный процесс |
| stable-diffusion-webui | AUTOMATIC1111/stable-diffusion-webui | AGPL-3.0 | внешний узел |
| react | react/react | MIT | зависимость |
| shadcn-ui | shadcn-ui/ui | MIT | зависимость |
| next.js | vercel/next.js | MIT | зависимость |
| excalidraw | excalidraw/excalidraw | MIT | зависимость |
| scrcpy | Genymobile/scrcpy | Apache-2.0 | адаптер |
| rustdesk | rustdesk/rustdesk | AGPL-3.0 | внешний узел |
| linux | torvalds/linux | GPL-2.0 (в `COPYING`; API: NOASSERTION) | субстрат |
| kubernetes | kubernetes/kubernetes | Apache-2.0 | субстрат |
| node | nodejs/node | MIT (в `LICENSE`; API: NOASSERTION) | субстрат |
| go | golang/go | BSD-3-Clause | субстрат |
| rust | rust-lang/rust | MIT OR Apache-2.0 | субстрат |
| Awesome-Hacking | Hack-with-Github/Awesome-Hacking | CC0-1.0 | база знаний |
| developer-roadmap | nilbuild/developer-roadmap | NOASSERTION | референс: только чтение |
| build-your-own-x | codecrafters-io/build-your-own-x | NOASSERTION — машиночитаемой LICENSE нет | обучение: только чтение |
| system-design-primer | donnemartin/system-design-primer | NOASSERTION — машиночитаемой LICENSE нет | обучение: только чтение |
| prompts.chat | f/prompts.chat | NOASSERTION — не распознан API | обучение: только чтение |
| ossu/computer-science | ossu/computer-science | MIT | обучение |

MCP (Model Context Protocol) — открытый стандарт, используемый синапсами (ADR-0002).

Правило провенанса: в этот репозиторий не входит ни байт чужого кода, текстов, логотипов или медиа — органы присутствуют только как имена, ссылки и факты (см. [`PROVENANCE.md`](PROVENANCE.md)).
