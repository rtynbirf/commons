# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Валидатор конвейера COMMONS (SPEC-0007): артефакты n8n -> CheckResult.

Конвейер — данные (G2): docker-compose.yml и воркфлоу *.json; этот модуль —
только механизм проверки. Fail-closed (G1): отсутствующий файл, битый
JSON/YAML, неполная структура, неизвестный тип узла, команда вне белого
списка, привилегированный контейнер — отказ; молчаливых пропусков нет.
Без сети, времени и окружения — проверка воспроизводима байт-в-байт.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from dataclasses import dataclass

import yaml

# Белый список команд (SPEC-0007, п. 2): исполняющий узел зовёт только точки
# входа организма; аргументы допустимы, произвольный shell — нет.
WHITELIST_COMMANDS: tuple[str, ...] = (
    "commons-pid1",
    "commons-immune",
    "python3 -m immune",
    "python3 -m pipeline",
    "python3 -m pytest",
)

# Известные типы узлов n8n; всё прочее — отказ ('unknown-node', G1).
ALLOWED_NODE_TYPES: tuple[str, ...] = (
    "n8n-nodes-base.scheduleTrigger",
    "n8n-nodes-base.manualTrigger",
    "n8n-nodes-base.executeCommand",
    "n8n-nodes-base.set",
    "n8n-nodes-base.if",
    "n8n-nodes-base.noOp",
    "n8n-nodes-base.webhook",
)

# Запрещённые shell-метасимволы в команде исполняющего узла (SPEC-0007, п. 2);
# перевод строки — тоже метасимвол.
_FORBIDDEN: tuple[str, ...] = (";", "|", "&", "`", "$(", "\n", "\r")


@dataclass(frozen=True)
class CheckResult:
    """Вердикт валидатора по одному артефакту конвейера."""

    ok: bool
    artifact: str   # имя файла
    rule: str       # 'ok' | 'missing' | 'parse' | 'structure' | 'unknown-node' | 'command-not-allowed' | 'compose'
    reason: str     # человекочитаемо, по-русски


def _name(path: str | pathlib.Path) -> str:
    """Имя файла артефакта (без каталога): CheckResult.artifact и строки отчёта."""
    return pathlib.Path(path).name


def _blank(value: object) -> bool:
    """Поле пусто: None, не строка или одни пробелы."""
    return not isinstance(value, str) or not value.strip()


def _ok(artifact: str, reason: str) -> CheckResult:
    return CheckResult(True, artifact, "ok", reason)


def _fail(artifact: str, rule: str, reason: str) -> CheckResult:
    return CheckResult(False, artifact, rule, reason)


def _normalized(command: str) -> str:
    """Команда со схлопнутым whitespace (пробелы/табуляция — в одиночные пробелы)."""
    return " ".join(command.split())


def _command_allowed(command: str, commands: tuple[str, ...]) -> bool:
    """Точка входа распознаётся на границе токена: нормализованная команда
    равна записи белого списка ИЛИ начинается с неё как 'entry + пробел + аргументы'."""
    normalized = _normalized(command)
    return any(normalized == entry or normalized.startswith(entry + " ") for entry in commands)


def _check_node(
    node: object, artifact: str, commands: tuple[str, ...], types: tuple[str, ...]
) -> CheckResult | None:
    """Проверка одного узла воркфлоу; None — узел валиден.
    Порядок правил: structure (форма узла) -> unknown-node -> command-not-allowed.
    Лишние ключи узла (id, position, typeVersion, ...) не проверяются и разрешены.
    """
    if not isinstance(node, dict):
        return _fail(artifact, "structure", "узел — не словарь")
    if _blank(node.get("name")):
        return _fail(artifact, "structure", "у узла нет непустого имени ('name')")
    node_type = node.get("type")
    if not isinstance(node_type, str):
        return _fail(artifact, "structure", f"узел '{node.get('name')}': 'type' отсутствует или не строка")
    if not isinstance(node.get("parameters"), dict):
        return _fail(artifact, "structure", f"узел '{node.get('name')}': 'parameters' отсутствует или не словарь")
    if node_type not in types:
        known = ", ".join(types)
        return _fail(artifact, "unknown-node", f"узел '{node.get('name')}': неизвестный тип '{node_type}' (известные: {known})")
    if node_type.endswith("executeCommand"):
        command = node["parameters"].get("command")
        if _blank(command):
            return _fail(artifact, "command-not-allowed", f"узел '{node.get('name')}': 'parameters.command' отсутствует, пусто или не строка")
        for bad in _FORBIDDEN:
            if bad in command:
                label = "перевод строки" if bad in ("\n", "\r") else repr(bad)
                return _fail(
                    artifact,
                    "command-not-allowed",
                    f"узел '{node.get('name')}': команда содержит запрещённый shell-метасимвол {label}",
                )
        if not _command_allowed(command, commands):
            return _fail(
                artifact,
                "command-not-allowed",
                f"узел '{node.get('name')}': команда вне белого списка: '{_normalized(command)}'",
            )
    return None


def validate_workflow(
    path: str | pathlib.Path,
    commands: tuple[str, ...] = WHITELIST_COMMANDS,
    types: tuple[str, ...] = ALLOWED_NODE_TYPES,
) -> CheckResult:
    """Валидация воркфлоу (экспорт n8n, JSON). Правила по порядку, первый отказ
    возвращается: missing (файл не существует/не читается) -> parse (битый JSON)
    -> structure (верхний уровень — dict: 'name' — непустая str, 'nodes' —
    непустой list, 'connections' — dict; каждый узел — dict с 'name' (непустая
    str), 'type' (str), 'parameters' (dict)) -> unknown-node (тип вне
    ALLOWED_NODE_TYPES) -> command-not-allowed (команда узла executeCommand:
    непустая str, без shell-метасимволов, в белом списке на границе токена).
    Лишние ключи воркфлоу и узлов (id, position, settings, active, ...)
    разрешены — проверяются только структурные поля контракта (SPEC-0007).
    """
    artifact = _name(path)
    try:
        raw = pathlib.Path(path).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return _fail(artifact, "missing", "файл не существует или не читается (fail-closed)")
    try:
        data = json.loads(raw)
    except ValueError as exc:
        return _fail(artifact, "parse", f"невалидный JSON: {exc}")

    if not isinstance(data, dict):
        return _fail(artifact, "structure", "верхний уровень воркфлоу — не словарь")
    if _blank(data.get("name")):
        return _fail(artifact, "structure", "'name' отсутствует, пусто или не строка")
    nodes = data.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return _fail(artifact, "structure", "'nodes' отсутствует, пусто или не список")
    if not isinstance(data.get("connections"), dict):
        return _fail(artifact, "structure", "'connections' отсутствует или не словарь")

    for node in nodes:
        result = _check_node(node, artifact, commands, types)
        if result is not None:
            return result
    return _ok(artifact, f"воркфлоу валиден: узлов {len(nodes)}, команды в белом списке")


def validate_compose(path: str | pathlib.Path) -> CheckResult:
    """Валидация референс-развёртывания n8n (docker-compose.yml, YAML):
    dict; 'services' — dict; в нём есть сервис 'n8n'; его 'image' — строка
    с 'n8nio/n8n'; ни у одного сервиса нет включённого 'privileged'.
    Любое нарушение -> rule='compose'; битый YAML -> 'parse'; отсутствующий
    или нечитаемый файл -> 'missing' (fail-closed, G1).
    """
    artifact = _name(path)
    try:
        raw = pathlib.Path(path).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return _fail(artifact, "missing", "файл не существует или не читается (fail-closed)")
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        return _fail(artifact, "parse", f"невалидный YAML: {exc}")

    if not isinstance(data, dict):
        return _fail(artifact, "compose", "верхний уровень compose — не словарь")
    services = data.get("services")
    if not isinstance(services, dict) or not services:
        return _fail(artifact, "compose", "'services' отсутствует, пусто или не словарь")
    n8n = services.get("n8n")
    if not isinstance(n8n, dict):
        return _fail(artifact, "compose", "сервис 'n8n' отсутствует или не словарь")
    image = n8n.get("image")
    if not isinstance(image, str) or "n8nio/n8n" not in image:
        return _fail(artifact, "compose", f"образ сервиса 'n8n' — не строка с 'n8nio/n8n' (получено: {image!r})")
    for service_name, service in services.items():
        if isinstance(service, dict) and service.get("privileged"):
            return _fail(artifact, "compose", f"сервис '{service_name}' привилегирован ('privileged') — запрещено (SPEC-0007)")
    return _ok(artifact, f"сервис 'n8n' на образе '{image}'; привилегированных сервисов нет")


def _format(result: CheckResult) -> str:
    """Строка отчёта по артефакту: 'OK   <имя>' или 'FAIL <имя>: <rule> — <reason>'."""
    if result.ok:
        return f"OK   {result.artifact}"
    return f"FAIL {result.artifact}: {result.rule} — {result.reason}"


def run_check(workflows_dir: str | pathlib.Path, compose_path: str | pathlib.Path, out=print) -> int:
    """Гейт конвейера: проверить все *.json в workflows_dir (в отсортированном
    порядке) и compose_path. Вывод — по строке на артефакт (_format), в конце
    итог: при успехе 'PIPELINE: N ok, 0 failed' и код 0, иначе
    'PIPELINE: FAIL (ok=N, failed=M)' и код 1. Отсутствующий каталог воркфлоу —
    отказ ('missing'): артефакты конвейера не могут отсутствовать молча (G1).
    out — функция печати одной строки (по умолчанию print).
    """
    results: list[CheckResult] = []
    directory = pathlib.Path(workflows_dir)
    if directory.is_dir():
        results.extend(validate_workflow(path) for path in sorted(directory.glob("*.json")))
    else:
        results.append(_fail(str(directory), "missing", "каталог воркфлоу не существует (fail-closed: проверять нечего)"))
    results.append(validate_compose(compose_path))

    ok_count = 0
    failed = 0
    for result in results:
        out(_format(result))
        if result.ok:
            ok_count += 1
        else:
            failed += 1

    if failed:
        out(f"PIPELINE: FAIL (ok={ok_count}, failed={failed})")
        return 1
    out(f"PIPELINE: {ok_count} ok, {failed} failed")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI: python -m pipeline [--workflows DIR] [--compose FILE].
    По умолчанию — артефакты пакета относительно cwd (запуск из корня
    репозитория): pipeline/n8n/workflows и pipeline/n8n/docker-compose.yml."""
    parser = argparse.ArgumentParser(
        prog="python -m pipeline",
        description="Валидатор конвейера COMMONS (SPEC-0007): воркфлоу n8n и compose — данные, проверяемые как код.",
    )
    parser.add_argument(
        "--workflows", type=pathlib.Path, default=pathlib.Path("pipeline/n8n/workflows"),
        help="каталог с воркфлоу *.json (по умолчанию: pipeline/n8n/workflows)",
    )
    parser.add_argument(
        "--compose", type=pathlib.Path, default=pathlib.Path("pipeline/n8n/docker-compose.yml"),
        help="путь к референс-развёртыванию n8n (по умолчанию: pipeline/n8n/docker-compose.yml)",
    )
    args = parser.parse_args(argv)
    return run_check(args.workflows, args.compose)
