"""Адаптер-мост к openclaw gateway (SPEC-0008, ADR-0010): CLI вместо самодельного протокола.

Документация протокола openclaw запрещает hand-roll handshake клиентам вне официальных
TS-пакетов, поэтому организм вызывает `openclaw gateway call <method> --json`: метод —
из белого списка ALLOWED_METHODS, параметры — структурированный dict, сериализуемый
телом в один аргумент --params. Shell-строк не строится: subprocess вызывается списком
argv (shell=False), инъекция в значениях params остаётся данными JSON. openclaw — руки,
не второй ствол мозга: исполняет импульсы ствола, не решает (SPEC-0008). Живой gateway —
на хосте человека (PID 1); токен — только env хоста, в теле — имя переменной.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Optional

# Белый список методов (SPEC-0008, п. 3): расширение — только правкой спеки (G2);
# мост не знает ни одного метода сверх списка.
ALLOWED_METHODS: tuple[str, ...] = ("health", "status", "chat.send", "chat.abort")

DEFAULT_BINARY = "openclaw"
CALL_TIMEOUT_S = 20.0

# Инъекция runner'а: argv -> (rc, stdout, stderr). Тесты подставляют фейк —
# сеть CI не трогается (SPEC-0008, п. 7).
Runner = Callable[[list[str]], tuple[int, str, str]]


@dataclass(frozen=True)
class EffectorResult:
    """Вердикт одного вызова эффектора (G3: наблюдаемость).

    rule — правило исхода:
      ok                 — метод исполнен через gateway;
      method-not-allowed — метод вне белого списка SPEC-0008;
      params-type        — параметры не JSON-объект (dict);
      binary-missing     — бинарник CLI не найден на хосте;
      call-failed        — gateway вернул rc != 0 или превышен таймаут;
      parse              — stdout gateway не JSON.
    """

    ok: bool
    method: str
    payload: Any
    rule: str    # 'ok' | 'method-not-allowed' | 'params-type' | 'binary-missing' | 'call-failed' | 'parse'
    reason: str  # человекочитаемо, по-русски


class OpenClawAdapter:
    """Мост к openclaw gateway через CLI (ADR-0010).

    entry — запись органа из synapse/mcp-manifest.yaml (как у OllamaAdapter):
    бинарник берётся из entry['binary'], иначе — параметр binary. runner —
    инъекция запуска subprocess для тестов; по умолчанию default_runner.
    """

    def __init__(
        self,
        entry: dict[str, Any] | None = None,
        runner: Runner | None = None,
        binary: str = DEFAULT_BINARY,
    ) -> None:
        self.entry = entry or {}  # идентичность (SPEC-0002 п.9): шлюз сверяет entry["name"]
        self.binary = (entry or {}).get("binary") or binary
        self.runner: Runner = runner or default_runner

    def call(self, method: str, params: dict[str, Any] | None = None) -> EffectorResult:
        """Исполнить метод gateway'а. Fail-closed (G1): любое нарушение — отказ
        без запуска бинарника. Порядок гейтов: method-not-allowed -> params-type
        -> binary-missing / call-failed -> parse -> ok."""
        if method not in ALLOWED_METHODS:
            return EffectorResult(
                False,
                method,
                None,
                "method-not-allowed",
                f"метод '{method}' вне белого списка SPEC-0008 (разрешены: {', '.join(ALLOWED_METHODS)})",
            )
        if params is not None and not isinstance(params, dict):
            return EffectorResult(
                False,
                method,
                None,
                "params-type",
                "параметры должны быть JSON-объектом (dict), строки shell не принимаются",
            )
        argv = [self.binary, "gateway", "call", method, "--json"]
        if params is not None:
            argv += ["--params", json.dumps(params, ensure_ascii=False)]
        # subprocess — списком argv (shell=False): значения params остаются данными
        # JSON, shell-строка не строится (ADR-0010).
        try:
            rc, stdout, stderr = self.runner(argv)
        except FileNotFoundError:
            return EffectorResult(
                False,
                method,
                None,
                "binary-missing",
                f"бинарник '{self.binary}' не найден: живой gateway — на хосте человека (PID 1)",
            )
        except subprocess.TimeoutExpired:
            return EffectorResult(
                False,
                method,
                None,
                "call-failed",
                "вызов gateway превысил таймаут 20 с",
            )
        if rc != 0:
            return EffectorResult(
                False,
                method,
                None,
                "call-failed",
                f"gateway вернул код {rc}: {(stderr or stdout).strip()[:200]}",
            )
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return EffectorResult(False, method, None, "parse", "stdout gateway не JSON")
        return EffectorResult(True, method, payload, "ok", "метод исполнен через gateway")

    def health(self) -> EffectorResult:
        """Пульс gateway: метод health из белого списка."""
        return self.call("health")

    def status(self) -> EffectorResult:
        """Состояние gateway и сессий: метод status из белого списка."""
        return self.call("status")

    def send_message(
        self,
        text: str,
        session_key: str | None = None,
        idempotency_key: str | None = None,
    ) -> EffectorResult:
        """Импульс в канал человека: chat.send уходит закрытым объектом
        (SPEC-0008, п. 4): sessionKey + message + idempotencyKey. Ключ
        идемпотентности генерирует тело (uuid4) на каждый импульс — повторный
        пульс не дублирует сообщение человеку."""
        if not isinstance(text, str) or not text.strip():
            return EffectorResult(
                False,
                "chat.send",
                None,
                "params-type",
                "текст сообщения обязателен и не пуст",
            )
        params = {
            "sessionKey": session_key or os.environ.get("COMMONS_OPENCLAW_SESSION") or "main",
            "message": text,
            "idempotencyKey": idempotency_key or str(uuid.uuid4()),
        }
        return self.call("chat.send", params)


def default_runner(argv: list[str]) -> tuple[int, str, str]:
    """Запуск CLI списком argv (shell=False), таймаут CALL_TIMEOUT_S: (rc, stdout, stderr)."""
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=CALL_TIMEOUT_S)
    return proc.returncode, proc.stdout, proc.stderr


def main(argv: list[str] | None = None) -> int:
    """CLI рук организма: python3 -m openclaw <command> [опции].

    Примеры:
        python3 -m openclaw health
        python3 -m openclaw status
        python3 -m openclaw send --text "импульс доставлен"
        python3 -m openclaw send --text "..." --session alerts --idem 3f2c9e4a-...
        python3 -m openclaw abort --run 2026-11-02-pid1
        python3 -m openclaw abort --params '{"runId": "2026-11-02-pid1"}'
        python3 -m openclaw check [--policy openclaw/reference/effector-policy.json]

    Вывод (G3): при успехе 'OPENCLAW: ok <method> <payload>' и код 0,
    при отказе 'OPENCLAW: FAIL (<rule>) <причина>' и код 1.
    """
    parser = argparse.ArgumentParser(
        prog="python3 -m openclaw",
        description="Эффектор openclaw (SPEC-0008, ADR-0010): вызов gateway через CLI, белый список методов, fail-closed.",
    )
    parser.add_argument(
        "command",
        choices=("health", "status", "send", "abort", "check"),
        help="метод эффекта (check — валидация данных-политики эффекта, openclaw.check)",
    )
    parser.add_argument("--text", default=None, help="текст сообщения (для send)")
    parser.add_argument("--session", default=None, help="sessionKey чата (по умолчанию: COMMONS_OPENCLAW_SESSION или main)")
    parser.add_argument("--idem", default=None, help="idempotencyKey (по умолчанию: uuid4 на каждый импульс)")
    parser.add_argument("--run", default=None, help="идентификатор прогона (для abort)")
    parser.add_argument("--binary", default=DEFAULT_BINARY, help=f"бинарник CLI (по умолчанию: {DEFAULT_BINARY})")
    parser.add_argument("--params", default=None, help="JSON-объект параметров (для abort и прочих методов; только dict)")
    parser.add_argument("--policy", default="openclaw/reference/effector-policy.json", help="файл политики эффекта (для check)")
    args = parser.parse_args(argv)

    if args.command == "check":
        from .check import run_check  # локальный импорт: check.py импортирует adapter

        return run_check(args.policy)

    adapter = OpenClawAdapter(binary=args.binary)
    result: EffectorResult
    if args.command == "health":
        result = adapter.health()
    elif args.command == "status":
        result = adapter.status()
    elif args.command == "send":
        if args.text is None:
            result = EffectorResult(
                False, "chat.send", None, "params-type", "текст сообщения обязателен и не пуст"
            )
        else:
            result = adapter.send_message(args.text, args.session, args.idem)
    else:  # abort
        raw_params: Optional[str] = args.params
        candidate: Any = None
        if raw_params:
            try:
                candidate = json.loads(raw_params)
            except json.JSONDecodeError:
                candidate = None  # не JSON -> не dict -> params-type
        elif args.run is not None:
            candidate = {"runId": args.run}
        if isinstance(candidate, dict):
            result = adapter.call("chat.abort", candidate)
        else:
            result = EffectorResult(
                False,
                "chat.abort",
                None,
                "params-type",
                "для abort нужен --run <идентификатор прогона> или --params '<json-объект>'",
            )

    if result.ok:
        print(f"OPENCLAW: ok {result.method} {json.dumps(result.payload, ensure_ascii=False)}")
        return 0
    print(f"OPENCLAW: FAIL ({result.rule}) {result.reason}")
    return 1
