"""Валидатор данных-политики эффекта (SPEC-0008): effector-policy.json -> CheckResult.

Политика эффекта — данные (G2): адрес gateway, привязка, имя env-переменной токена,
белый список методов, требование approvals на exec; этот модуль — только механизм
проверки. Fail-closed (G1): отсутствующий файл, битый JSON, неполная структура,
bind не loopback, токен в данных, метод вне белого списка, exec без approvals —
отказ; молчаливых пропусков нет. Без сети, времени и окружения — проверка
воспроизводима байт-в-байт.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .adapter import ALLOWED_METHODS

REQUIRED_POLICY: tuple[str, ...] = (
    "gateway_url",
    "bind",
    "auth_token_env",
    "allowed_methods",
    "exec_approval_required",
)

# Имя env-переменной (не значение токена): секреты не в теле (SPEC-0008, п. 5).
_AUTH_ENV_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")


@dataclass(frozen=True)
class CheckResult:
    """Вердикт валидатора по одному артефакту политики эффекта."""

    ok: bool
    artifact: str  # путь к файлу политики
    rule: str      # 'ok' | 'missing' | 'parse' | 'structure' | 'bind-open' | 'auth-weak' | 'method-unknown' | 'exec-open'
    reason: str    # человекочитаемо, по-русски


def validate_policy(path: str | Path) -> CheckResult:
    """Валидация данных-политики эффекта (JSON). Правила по порядку, первый отказ
    возвращается (SPEC-0008, §4): missing (файл не существует) -> parse (битый
    JSON) -> structure (JSON-объект со всеми полями REQUIRED_POLICY) -> bind-open
    (bind != 'loopback') -> auth-weak (auth_token_env — не имя env-переменной) ->
    method-unknown (метод вне ALLOWED_METHODS) -> exec-open
    (exec_approval_required не True); иначе ok. Лишние ключи политики разрешены.
    """
    path = Path(path)
    if not path.is_file():
        return CheckResult(False, str(path), "missing", f"файл политики отсутствует: {path}")
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return CheckResult(False, str(path), "missing", f"файл политики не существует или не читается: {path}")
    try:
        data = json.loads(raw)
    except ValueError as exc:
        return CheckResult(False, str(path), "parse", f"файл политики не JSON: {exc}")

    if not isinstance(data, dict) or any(key not in data for key in REQUIRED_POLICY):
        return CheckResult(
            False,
            str(path),
            "structure",
            f"политика должна быть JSON-объектом с полями: {', '.join(REQUIRED_POLICY)}",
        )

    if data["bind"] != "loopback":
        return CheckResult(
            False,
            str(path),
            "bind-open",
            "gateway должен быть привязан к loopback (bind: loopback) — CVE-2026-25253: открытый порт gateway недопустим",
        )

    auth = data["auth_token_env"]
    if not isinstance(auth, str) or not auth.strip() or not _AUTH_ENV_RE.fullmatch(auth):
        return CheckResult(
            False,
            str(path),
            "auth-weak",
            "auth_token_env должно быть ИМЕНЕМ env-переменной (например OPENCLAW_GATEWAY_TOKEN), а не значением токена",
        )

    methods = data["allowed_methods"]
    if not isinstance(methods, list) or not methods:
        return CheckResult(
            False,
            str(path),
            "method-unknown",
            f"allowed_methods должен быть непустым списком методов из белого списка SPEC-0008 (разрешены: {', '.join(ALLOWED_METHODS)})",
        )
    for method in methods:
        if method not in ALLOWED_METHODS:
            return CheckResult(
                False,
                str(path),
                "method-unknown",
                f"метод '{method}' вне белого списка SPEC-0008 (разрешены: {', '.join(ALLOWED_METHODS)})",
            )

    if data["exec_approval_required"] is not True:
        return CheckResult(
            False,
            str(path),
            "exec-open",
            "exec-команды openclaw допускаются только под approvals человека (exec_approval_required: true)",
        )

    return CheckResult(True, str(path), "ok", "политика эффекта соответствует SPEC-0008")


def run_check(policy_path: str | Path, out: Callable[[str], None] = print) -> int:
    """Гейт политики эффекта: один артефакт — один вердикт. При успехе
    'POLICY: 1 ok, 0 failed' и код 0; иначе строка '  <rule>: <reason> [<артефакт>]'
    и код 1 (G1, G3). out — функция печати одной строки (по умолчанию print).
    """
    result = validate_policy(policy_path)
    out(f"POLICY: {1 if result.ok else 0} ok, {0 if result.ok else 1} failed")
    if not result.ok:
        out(f"  {result.rule}: {result.reason} [{result.artifact}]")
    return 0 if result.ok else 1


def main(argv: list[str] | None = None) -> int:
    """CLI: python3 -m openclaw check [--policy FILE] — валидация политики эффекта.
    По умолчанию — артефакт пакета относительно cwd (запуск из корня репозитория):
    openclaw/reference/effector-policy.json."""
    parser = argparse.ArgumentParser(
        prog="python3 -m openclaw check",
        description="Валидатор данных-политики эффектора (SPEC-0008): артефакты — данные, fail-closed.",
    )
    parser.add_argument(
        "--policy",
        default="openclaw/reference/effector-policy.json",
        help="путь к файлу политики (по умолчанию: openclaw/reference/effector-policy.json)",
    )
    args = parser.parse_args(argv)
    return run_check(args.policy)
