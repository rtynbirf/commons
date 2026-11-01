# Живая верификация рейтинга — 2026-11-01

Статус: действует · Дата проверки: 2026-11-01

Снимок топ-100 от 26.10.2026 (`organs/top100-2026-10-26.yaml`) — это снимок. 2026-11-01 ключевые
позиции перепроверены живым GitHub API (аутентифицированные запросы `GET /repos/{owner}/{repo}`).
Вывод из сверки записан в конце — он важнее самих чисел.

## Дельты ключевых органов (26.10 → 01.11)

| Орган | Снимок 26.10 | Живой API 01.11 | Лицензия (API) |
|---|---:|---:|---|
| morluto/rea | 389 257 | **417 492** (+28 235 за 6 дней) | MIT |
| obra/superpowers | 305 417 | 310 406 | MIT |
| NousResearch/hermes-agent | — (вне топ-100) | 259 386 | MIT |
| openclaw/openclaw | 393 128 | 393 625 | MIT |
| react/react | 251 864 | 252 069 | MIT |
| codecrafters-io/build-your-own-x | 556 359 | 558 048 | NOASSERTION |
| n8n-io/n8n | 208 643 | 209 269 | NOASSERTION (fair-code) |
| anthropics/skills | 183 913 | 186 151 | NOASSERTION (по-навыковые, ToU Anthropic) |
| ollama/ollama | 184 850 | 185 543 | MIT |
| microsoft/markitdown | 192 313 | 193 345 | MIT |
| firecrawl/firecrawl | 195 544 | 197 568 | AGPL-3.0 |
| langgenius/dify | 159 593 | 160 154 | NOASSERTION (Apache-2.0 с условиями) |
| huggingface/transformers | 168 192 | 168 412 | Apache-2.0 |
| langchain-ai/langchain | 148 491 | 148 813 | MIT |
| github/spec-kit | 142 980 | 144 756 | MIT |
| Graphify-Labs/graphify | 135 831 | 140 345 | Apache-2.0 |

## Владельцы и адреса — тоже ветки

За время жизни рейтинга части целого переезжали:

| Репозиторий | Было | Стало |
|---|---|---|
| react/react | facebook/react | организация `react` |
| anomalyco/opencode | sst/opencode | организация `anomalyco` |
| Comfy-Org/ComfyUI | comfyanonymous/ComfyUI | организация `Comfy-Org` |
| f/prompts.chat | f/awesome-chatgpt-prompts | переименование репозитория |
| nilbuild/developer-roadmap | kamranahmedse/developer-roadmap | смена владельца |

GitHub прозрачно редиректит старые адреса — обмен не рвётся при переезде. Инженерное следствие:
в реестрах (`organs/registry.yaml`) хранится slug на дату проверки + дата; резолвер должен следовать
редиректам, а «владелец» не считается частью идентичности органа. **Идентичность органа — его обмен,
а не адрес.**

## Инженерные следствия

1. `morluto/rea`: +7,3% звёзд за шесть дней — fastest-growing орган из ядра; референс обязателен.
2. Лицензии «по памяти» опасны: три из проверенных органов имеют NOASSERTION при живых лицензионных
   файлах, один (`anthropics/skills`) — по-навыковые условия использования. Иммунный барьер
   ([PROVENANCE.md](../PROVENANCE.md)) теперь опирается на верифицированную матрицу, а не на память.
3. Звёзды — температура, не диагноз: у `build-your-own-x` полмиллиона звёзд и нет машиночитаемой
   лицензии — это референс, не орган тела.

Метод: скрипт `verify_repos.py` (журнал вычислений ведётся вне репозитория); повтор сверки — при каждом
подключении органа.
