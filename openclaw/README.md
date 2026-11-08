# Эффектор: openclaw — руки организма

Спека: [SPEC-0008](../specs/SPEC-0008-effector.md) · ADR: [ADR-0010](../docs/adr/ADR-0010-cli-bridge-effector.md)

openclaw — персональный gateway между моделями и каналами человека (Telegram, WhatsApp,
Discord и др.). В организме это **эффектор**: доставляет импульсы ствола мозга в каналы,
где живёт человек. openclaw — руки, не второй ствол мозга: он исполняет, но не решает;
ответы канала входят в организм только как сенсорика следующего пульса.

Мост — CLI, не самодельный WebSocket (ADR-0010): организм вызывает
`openclaw gateway call <method> --json`, параметры — структурированный dict, сериализуемый
телом в один аргумент `--params`; subprocess вызывается списком argv. Shell-строки не
строятся — инъекция в значениях остаётся данными JSON.

## Развёртывание на хосте человека (PID 1, ADR-0006)

Тело ничего не встраивает (SPEC-0006): ни кода openclaw, ни npm-зависимостей. Живой
gateway человек разворачивает на своём хосте (верифицированные команды):

    npm install -g openclaw@latest
    openclaw onboard --install-daemon
    openclaw gateway start

Токен — только env хоста (в теле и артефактах — имя переменной, не значение):

    openclaw doctor --generate-gateway-token   # генерация токена gateway
    export OPENCLAW_GATEWAY_TOKEN=...          # читает gateway на хосте, не тело

Gateway по умолчанию привязан к loopback (127.0.0.1:18789).

## Как организм вызывает руки

    python3 -m openclaw health                 # пульс gateway
    python3 -m openclaw status                 # состояние сессий
    python3 -m openclaw send --text "..."      # импульс в канал (chat.send)
    python3 -m openclaw abort --run <id>       # прервать прогон (chat.abort)
    python3 -m openclaw check                  # валидация политики эффекта

Каждый вызов — импульс ствола мозга в конверте крови (SPEC-0003): cost — длительность
вызова, токенов у моста нет. `idempotencyKey` генерирует тело (uuid4) на каждый импульс —
повторный пульс не дублирует сообщение человеку. Сессия по умолчанию — `main`
(env `COMMONS_OPENCLAW_SESSION` переопределяет).

## Белый список методов

`health`, `status`, `chat.send`, `chat.abort` (SPEC-0008, п. 3). Мост не знает ни одного
метода сверх списка; расширение — только правкой спеки (G2: новая способность = строка
спеки, не код).

## Политика эффекта

`openclaw/reference/effector-policy.json` — данные: `bind: loopback`,
`auth_token_env: OPENCLAW_GATEWAY_TOKEN`, `exec_approval_required: true`. Проверка —
`python3 -m openclaw check` (fail-closed: missing, parse, structure, bind-open,
auth-weak, method-unknown, exec-open).

## Уроки безопасности (февраль 2026)

CVE-2026-25253 (RCE в gateway) и 341 вредоносный навык ClawHub показали цену свободной
поверхности действия: **auth обязательна даже на loopback**, exec — только под approvals
человека, поверхность эффекта — минимальный белый список. Нарушение политики — отказ.

## Ссылки

- Upstream: https://github.com/openclaw/openclaw
- SPEC-0006 (орган не встраивается) · SPEC-0003 (конверт крови) · ADR-0006 (человек = PID 1)
