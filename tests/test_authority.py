# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмка SPEC-0002 v0.4.0 «исполнение полномочий» (волна №7): страж, bind, грамматика, цикл.

Красная находка аудита волны №5: ренегат молча выходил за полномочия. Эти тесты
фиксируют КОНТРАКТ спеки, а не текущий код: страж полномочий на invoke (п.8),
исполнимая грамматика authority (п.8), идентичность bind_adapter (п.9), замена
при invoke-падении (отказные режимы), закрытие трейса циклом на AuthorityViolation.

Мини-манифесты собираются в tmp_path внутри тестов: conftest-манифест не тронут.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from blood.journal import Journal
from brainstem import Loop, Step
from synapse.gateway import (
    AuthorityViolation,
    Gateway,
    GatewayConfigError,
    OrganUnavailable,
)

from .fakes import FakeAbuser, FakeEcho, FakeFallen, FakeRenegade  # noqa: TID252

READ_ONLY = {"fs": "read-only", "network": "none", "process": "none"}
STRICT = {"fs": "none", "network": "none", "process": "none"}


@pytest.fixture()
def journal() -> Journal:
    return Journal()


def _organ(name: str, *, adapter: str, tools: list[str], authority: dict[str, Any]) -> dict[str, Any]:
    """Мини-запись манифеста со всеми обязательными полями (SPEC-0002 п.1)."""
    return {
        "name": name,
        "system": "senses",
        "mode": "dependency",
        "upstream": f"https://example.invalid/{name}",
        "license": "MIT",
        "transport": "stdio",
        "command": f"{name}-mcp",
        "healthcheck": "initialize handshake",
        "tools": tools,
        "authority": authority,
        "adapter": adapter,
    }


def _gateway(
    tmp_path: Path,
    journal: Journal,
    organs: list[dict[str, Any]],
    substitutions: dict[str, list[str]] | None = None,
) -> Gateway:
    path = tmp_path / "mcp-manifest.yaml"
    path.write_text(
        yaml.safe_dump({"organs": organs, "substitutions": substitutions or {}}, allow_unicode=True),
        encoding="utf-8",
    )
    return Gateway(path, journal)


def _adapter(gateway: Gateway, kind: type) -> Any:
    """Адаптер, собранный шлюзом из манифеста (ровно один экземпляр такого типа)."""
    found = [a for a in gateway.adapters if isinstance(a, kind)]
    assert found, f"шлюз не собрал адаптер {kind.__name__}"
    return found[0]


# --- a) ренегат fs: read-only: запись прервана до диска ----------------------


def test_renegade_fs_read_only_cannot_write(tmp_path: Path, journal: Journal) -> None:
    """Приёмка: ренегат fs: read-only не может записать файл — страж прерывает, кровь помнит (п.8; волна №5 перевёрнута)."""
    target = tmp_path / "loot.txt"
    gateway = _gateway(
        tmp_path,
        journal,
        [_organ("renegade", adapter="tests.fakes:FakeRenegade", tools=["smuggle_file"], authority=READ_ONLY)],
    )
    renegade = _adapter(gateway, FakeRenegade)

    with pytest.raises(AuthorityViolation):
        gateway.call("renegade", "smuggle_file", {"path": str(target)}, "auth-fs")

    assert not target.exists(), "страж пропустил запись: контрабанда оказалась на диске"
    assert renegade.crimes == [], "вызов прерван не ДО записи: ренегат успел"
    (violation,) = journal.by_type("security.violation")
    assert violation["organ"] == "renegade" and violation["trace_id"] == "auth-fs"
    assert not journal.by_type("act"), "нарушенный вызов не должен попадать в кровь как act"


# --- b) ренегат network: none: соединение прервано ---------------------------


def test_renegade_network_none_cannot_connect(tmp_path: Path, journal: Journal) -> None:
    """Приёмка: ренегат network: none не может открыть соединение — страж прерывает, кровь помнит (п.8, таблица network)."""
    gateway = _gateway(
        tmp_path,
        journal,
        [_organ("renegade", adapter="tests.fakes:FakeRenegade", tools=["phone_home"], authority=READ_ONLY)],
    )
    renegade = _adapter(gateway, FakeRenegade)

    with pytest.raises(AuthorityViolation):
        gateway.call("renegade", "phone_home", {}, "auth-net")

    assert renegade.crimes == [], "соединение успело открыться: прерывание после факта"
    (violation,) = journal.by_type("security.violation")
    assert violation["organ"] == "renegade" and violation["trace_id"] == "auth-net"
    assert not journal.by_type("act"), "нарушенный вызов не должен попадать в кровь как act"


# --- c) законный орган: страж не мешает ---------------------------------------


def test_lawful_organ_is_not_disturbed(tmp_path: Path, journal: Journal) -> None:
    """Приёмка/п.4: страж не мешает законной работе — эхо-орган с минимумом полномочий честно отвечает."""
    gateway = _gateway(
        tmp_path,
        journal,
        [_organ("quiet", adapter="tests.fakes:FakeEcho", tools=["echo"], authority={"fs": "none", "network": "none"})],
    )

    result = gateway.call("quiet", "echo", {"data": "законно"}, "auth-lawful")

    assert result["echo"] == {"data": "законно"}
    (act,) = journal.by_type("act")
    assert act["organ"] == "quiet" and act["trace_id"] == "auth-lawful"
    assert not journal.by_type("security.violation"), "страж тронул законный вызов"


# --- d) fs: none запрещает и чтение -------------------------------------------


def test_fs_none_forbids_even_reading(tmp_path: Path, journal: Journal) -> None:
    """Приёмка/п.8 (таблица fs): при none прерывается и чтение — файл-жертва существует, но не прочитан."""
    victim = tmp_path / "secret.txt"
    victim.write_text("секрет", encoding="utf-8")
    gateway = _gateway(
        tmp_path,
        journal,
        [_organ("renegade", adapter="tests.fakes:FakeRenegade", tools=["read_thing"], authority=STRICT)],
    )
    renegade = _adapter(gateway, FakeRenegade)

    with pytest.raises(AuthorityViolation):
        gateway.call("renegade", "read_thing", {"path": str(victim)}, "auth-read")

    assert victim.exists() and victim.read_text(encoding="utf-8") == "секрет", "страж испортил жертву"
    assert renegade.crimes == [], "чтение успело состояться"
    (violation,) = journal.by_type("security.violation")
    assert violation["organ"] == "renegade"


# --- e) invoke-падение обслуживается резервом ---------------------------------


def test_invoke_fall_is_served_by_reserve(tmp_path: Path, journal: Journal) -> None:
    """Приёмка: орган, упавший при invoke, обслуживается резервом с organ.replace — как неотвечающий healthcheck'ом (отказные режимы)."""
    organs = [
        _organ("fallen", adapter="tests.fakes:FakeFallen", tools=["echo"], authority=STRICT),
        _organ("reserve", adapter="tests.fakes:FakeEcho", tools=["echo"], authority=STRICT),
    ]
    gateway = _gateway(tmp_path, journal, organs, substitutions={"fallen": ["reserve"]})

    result = gateway.call("fallen", "echo", {"data": "задача"}, "auth-fall")

    assert result["echo"] == {"data": "задача"}, "резерв не обслужил вызов"
    (failure,) = journal.by_type("error")
    assert failure["organ"] == "fallen"
    (replacement,) = journal.by_type("organ.replace")
    assert replacement["payload"] == {"from": "fallen", "to": "reserve"}


# --- f) invoke-падение без замены ---------------------------------------------


def test_invoke_fall_without_reserve_is_unavailable(tmp_path: Path, journal: Journal) -> None:
    """Отказной режим: падение при invoke без замен — error и OrganUnavailable, замена молча не выдумывается."""
    gateway = _gateway(
        tmp_path,
        journal,
        [_organ("fallen", adapter="tests.fakes:FakeFallen", tools=["echo"], authority=STRICT)],
    )

    with pytest.raises(OrganUnavailable):
        gateway.call("fallen", "echo", {}, "auth-alone")

    assert journal.by_type("error"), "падение органа прошло молча: нет события error"
    assert not journal.by_type("organ.replace"), "замена выдумана без таблицы substitutions"


# --- g) bind-самозванец --------------------------------------------------------


def test_bind_impostor_rejected_previous_binding_alive(tmp_path: Path, journal: Journal) -> None:
    """Приёмка/п.9: самозванец (чужое entry["name"]) отклоняется bind_adapter'ом до вызова; прежняя привязка жива."""
    gateway = _gateway(
        tmp_path,
        journal,
        [_organ("sense-a", adapter="tests.fakes:FakeEcho", tools=["echo"], authority=STRICT)],
    )
    original = gateway.adapters[0]
    impostor = FakeEcho({"name": "reserve-c"})

    with pytest.raises(GatewayConfigError):
        gateway.bind_adapter("sense-a", impostor)

    assert gateway.adapters[0] is original, "самозванец всё же сменил привязку"
    result = gateway.call("sense-a", "echo", {"data": "ok"}, "auth-bind")
    assert result["echo"] == {"data": "ok"}
    assert original.calls, "вызов обслужила не прежняя привязка"


# --- h) bind-безымянный --------------------------------------------------------


def test_bind_nameless_adapter_rejected(tmp_path: Path, journal: Journal) -> None:
    """Приёмка/п.9: безымянный адаптер (без entry) отклоняется до любого вызова."""
    gateway = _gateway(
        tmp_path,
        journal,
        [_organ("sense-a", adapter="tests.fakes:FakeEcho", tools=["echo"], authority=STRICT)],
    )
    original = gateway.adapters[0]

    with pytest.raises(GatewayConfigError):
        gateway.bind_adapter("sense-a", object())

    assert gateway.adapters[0] is original, "безымянный адаптер сменил привязку"
    assert gateway.call("sense-a", "echo", {"data": "ок"}, "auth-nameless")["echo"] == {"data": "ок"}


# --- i) невалидная грамматика authority ----------------------------------------


@pytest.mark.parametrize(
    "authority",
    [
        pytest.param({"fs": "read-only-input-dir", "network": "none", "process": "none"}, id="старый-неисполнимый-ярлык"),
        pytest.param({"fs": "walrus", "network": "none", "process": "none"}, id="неизвестный-ярлык-fs"),
        pytest.param({"fs": "none", "network": {"hosts": []}, "process": "none"}, id="network-с-пустым-hosts"),
    ],
)
def test_unexecutable_authority_grammar_blocks_startup(
    tmp_path: Path, journal: Journal, authority: dict[str, Any]
) -> None:
    """Приёмка/п.8: грамматика authority исполнима и проверяется при старте — манифест не валиден, шлюз не стартует."""
    with pytest.raises(GatewayConfigError):
        _gateway(
            tmp_path,
            journal,
            [_organ("any", adapter="tests.fakes:FakeEcho", tools=["echo"], authority=authority)],
        )


# --- j) цикл закрывает трейс на нарушении полномочий ---------------------------


def test_loop_closes_trace_on_authority_violation(tmp_path: Path, journal: Journal) -> None:
    """Приёмка/п.8: AuthorityViolation не покидает цикл молча — reflect (satisfied False) + halt, трейс полон для G1."""
    target = tmp_path / "loot.txt"
    gateway = _gateway(
        tmp_path,
        journal,
        [_organ("renegade", adapter="tests.fakes:FakeRenegade", tools=["smuggle_file"], authority=READ_ONLY)],
    )
    renegade = _adapter(gateway, FakeRenegade)
    loop = Loop(gateway, journal)
    plan = [Step(organ="renegade", tool="smuggle_file", payload={"path": str(target)}, intent="украсти файл")]

    outcome = loop.run(plan, trace_id="auth-loop")

    assert outcome is False, "цикл отчитался успехом после нарушения полномочий"
    assert not target.exists() and renegade.crimes == [], "страж не прервал вызов внутри цикла"
    events = journal.by_trace("auth-loop")
    assert [e["type"] for e in events] == ["plan", "security.violation", "reflect", "halt"]
    (reflect,) = [e for e in events if e["type"] == "reflect"]
    assert reflect["payload"]["satisfied"] is False
    assert "security" in reflect["payload"]["reason"].lower(), "reflect не называет нарушение безопасности"
    assert len([e for e in events if e["type"] == "halt"]) == 1, "halt обязан быть ровно один"
    assert all(e["trace_id"] == "auth-loop" for e in journal.all()), "трейс не полон для G1-реконструкции"


# --- j-bis) контракт цикла на нарушении, изолированный от стража ---------------


def test_loop_closes_trace_when_violation_raised_explicitly(tmp_path: Path, journal: Journal) -> None:
    """Диагностика той же приёмки: орган САМ бросает AuthorityViolation — цикл обязан закрыть трейс reflect+halt.

    Отличается от теста выше источником нарушения: здесь страж-перехватчик не нужен,
    так изолируется контракт ствола (reflect+halt) от контракта стража (прерывание invoke).
    """
    gateway = _gateway(
        tmp_path,
        journal,
        [_organ("abuser", adapter="tests.fakes:FakeAbuser", tools=["escape"], authority=STRICT)],
    )
    loop = Loop(gateway, journal)
    plan = [Step(organ="abuser", tool="escape", payload={}, intent="проверить стража")]

    assert loop.run(plan, trace_id="auth-abuser") is False, "цикл отчитался успехом после нарушения полномочий"
    events = journal.by_trace("auth-abuser")
    assert [e["type"] for e in events] == ["plan", "security.violation", "reflect", "halt"]
    (reflect,) = [e for e in events if e["type"] == "reflect"]
    assert reflect["payload"]["satisfied"] is False
    assert "security" in reflect["payload"]["reason"].lower()
    assert len([e for e in events if e["type"] == "halt"]) == 1
    assert all(e["trace_id"] == "auth-abuser" for e in journal.all())


# --- k) замена при invoke-падении через цикл -----------------------------------


def test_loop_survives_invoke_fall_via_reserve(tmp_path: Path, journal: Journal) -> None:
    """Приёмка: замена при invoke-падении не молчит — цикл доводит задачу резервом, organ.replace в крови."""
    organs = [
        _organ("fallen", adapter="tests.fakes:FakeFallen", tools=["echo"], authority=STRICT),
        _organ("reserve", adapter="tests.fakes:FakeEcho", tools=["echo"], authority=STRICT),
    ]
    gateway = _gateway(tmp_path, journal, organs, substitutions={"fallen": ["reserve"]})
    loop = Loop(gateway, journal)
    plan = [Step(organ="fallen", tool="echo", payload={"data": "задача"}, intent="работа при падении органа")]

    assert loop.run(plan, trace_id="auth-reserve") is True, "цикл не довёл задачу резервом"
    (replacement,) = journal.by_type("organ.replace")
    assert replacement["payload"] == {"from": "fallen", "to": "reserve"}
    (reflect,) = journal.by_type("reflect")
    assert reflect["payload"]["satisfied"] is True


# --- l) скоупы v0.5.0 (волна №9): страж знает пути и порты ---------------------


def test_scoped_fs_write_inside_scope_is_alive(tmp_path: Path, journal: Journal) -> None:
    """Приёмка v0.5.0: запись внутри заявленного корня жива — скоуп не ломает честную работу."""
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    gateway = _gateway(
        tmp_path,
        journal,
        [_organ("scoped", adapter="tests.fakes:FakeRenegade", tools=["smuggle_file"],
                authority={"fs": {"mode": "read-write", "paths": [str(downloads)]}, "network": "none", "process": "none"})],
    )
    result = gateway.call("scoped", "smuggle_file", {"path": str(downloads / "ok.txt")}, "scope-in")
    assert result == {"smuggled": True}
    assert (downloads / "ok.txt").read_text(encoding="utf-8") == "контрабанда"
    assert not journal.by_type("security.violation")
    (act,) = journal.by_type("act")
    assert act["trace_id"] == "scope-in"


def test_scoped_fs_write_outside_scope_is_interrupted(tmp_path: Path, journal: Journal) -> None:
    """Приёмка v0.5.0: ренегат со скоупом пишет вне каталога — security.violation, файл не создан."""
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    target = tmp_path / "outside.txt"
    gateway = _gateway(
        tmp_path,
        journal,
        [_organ("scoped", adapter="tests.fakes:FakeRenegade", tools=["smuggle_file"],
                authority={"fs": {"mode": "read-write", "paths": [str(downloads)]}, "network": "none", "process": "none"})],
    )
    renegade = _adapter(gateway, FakeRenegade)

    with pytest.raises(AuthorityViolation):
        gateway.call("scoped", "smuggle_file", {"path": str(target)}, "scope-out")

    assert not target.exists(), "страж пропустил запись вне корня"
    assert renegade.crimes == [], "запись успела случиться до прерывания"
    (violation,) = journal.by_type("security.violation")
    assert violation["organ"] == "scoped" and not journal.by_type("act")


def test_scoped_fs_read_only_blocks_write_inside_root(tmp_path: Path, journal: Journal) -> None:
    """Приёмка v0.5.0: read-only-скоуп — чтение внутри живо, запись внутри прервана."""
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (downloads / "note.txt").write_text("заметка", encoding="utf-8")
    gateway = _gateway(
        tmp_path,
        journal,
        [_organ("reader", adapter="tests.fakes:FakeRenegade", tools=["read_thing", "smuggle_file"],
                authority={"fs": {"mode": "read-only", "paths": [str(downloads)]}, "network": "none", "process": "none"})],
    )
    result = gateway.call("reader", "read_thing", {"path": str(downloads / "note.txt")}, "scope-ro-read")
    assert result["read"] == "заметка"
    with pytest.raises(AuthorityViolation):
        gateway.call("reader", "smuggle_file", {"path": str(downloads / "nope.txt")}, "scope-ro-write")
    assert not (downloads / "nope.txt").exists()


def test_scoped_fs_python_runtime_reads_survive(tmp_path: Path, journal: Journal) -> None:
    """Приёмка v0.5.0: исключение рантайма Python живо и при скоупе — иначе орган не жив."""
    import os as _os

    gateway = _gateway(
        tmp_path,
        journal,
        [_organ("reader", adapter="tests.fakes:FakeRenegade", tools=["read_thing"],
                authority={"fs": {"mode": "read-only", "paths": [str(tmp_path)]}, "network": "none", "process": "none"})],
    )
    stdlib_file = _os.__file__
    result = gateway.call("reader", "read_thing", {"path": str(stdlib_file)}, "scope-runtime")
    assert "read" in result


def test_scoped_fs_symlink_escape_is_closed(tmp_path: Path, journal: Journal) -> None:
    """Приёмка v0.5.0: симлинк внутри корня, цель вне — страж сверяет realpath и прерывает."""
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("секрет", encoding="utf-8")
    bait = downloads / "bait.txt"
    bait.symlink_to(secret)
    gateway = _gateway(
        tmp_path,
        journal,
        [_organ("scoped", adapter="tests.fakes:FakeRenegade", tools=["smuggle_file"],
                authority={"fs": {"mode": "read-write", "paths": [str(downloads)]}, "network": "none", "process": "none"})],
    )

    with pytest.raises(AuthorityViolation):
        gateway.call("scoped", "smuggle_file", {"path": str(bait)}, "scope-link")

    assert secret.read_text(encoding="utf-8") == "секрет", "симлинк-побег доёл файл"
    assert not journal.by_type("act")


def test_scoped_fs_rename_outside_root_interrupted(tmp_path: Path) -> None:
    """Приёмка v0.5.0: мутации при скоупе — rename с целью вне корня прерван, внутри жив."""
    import os as _os

    from synapse.authority import enforce, normalize

    root = tmp_path / "scope"
    root.mkdir()
    (root / "a.txt").write_text("a", encoding="utf-8")
    authority = normalize({"fs": {"mode": "read-write", "paths": [str(root)]}})
    with pytest.raises(AuthorityViolation):
        with enforce(authority, "mutator"):
            _os.rename(root / "a.txt", tmp_path / "b.txt")
    assert (root / "a.txt").exists(), "файл переехал вопреки скоупу"
    with enforce(authority, "mutator"):
        _os.rename(root / "a.txt", root / "c.txt")
    assert (root / "c.txt").exists()


def test_ports_scope_declared_alive_undeclared_interrupted(tmp_path: Path, journal: Journal) -> None:
    """Приёмка v0.5.0: {hosts, ports} — заявленный порт жив, незаявленный прерван ДО попытки."""
    import socket as _socket

    listener = _socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    open_port = listener.getsockname()[1]
    try:
        gateway = _gateway(
            tmp_path,
            journal,
            [_organ("porty", adapter="tests.fakes:FakeRenegade", tools=["phone_home", "dial_dns"],
                    authority={"fs": "none", "network": {"hosts": ["127.0.0.1"], "ports": [open_port]}, "process": "none"})],
        )
        result = gateway.call("porty", "phone_home", {"host": "127.0.0.1", "port": open_port}, "port-ok")
        assert result["phoned"] is True
        porty = _adapter(gateway, FakeRenegade)
        with pytest.raises(AuthorityViolation):
            gateway.call("porty", "phone_home", {"host": "127.0.0.1", "port": open_port + 1}, "port-bad")
        assert porty.crimes == [f"connected:127.0.0.1:{open_port}"], "коннект на незаявленный порт успел случиться"
        (violation,) = [e for e in journal.by_type("security.violation")]
        assert violation["trace_id"] == "port-bad"
    finally:
        listener.close()


def test_ports_scope_dns_carries_only_host(tmp_path: Path, journal: Journal) -> None:
    """Приёмка v0.5.0: getaddrinfo не несёт порта — хостовое правило, портовое не применяется."""
    gateway = _gateway(
        tmp_path,
        journal,
        [_organ("porty", adapter="tests.fakes:FakeRenegade", tools=["dial_dns"],
                authority={"fs": "none", "network": {"hosts": ["localhost"], "ports": [11434]}, "process": "none"})],
    )
    result = gateway.call("porty", "dial_dns", {"host": "localhost"}, "dns-ok")
    assert result["resolved"] is True
    with pytest.raises(AuthorityViolation):
        gateway.call("porty", "dial_dns", {"host": "example.invalid"}, "dns-bad")


@pytest.mark.parametrize(
    ("authority", "почему"),
    [
        ({"fs": "none", "network": {"ports": [80]}, "process": "none"}, "ports без hosts"),
        ({"fs": "none", "network": {"hosts": ["h"], "ports": ["80"]}, "process": "none"}, "порт-строка"),
        ({"fs": "none", "network": {"hosts": ["h"], "ports": [0]}, "process": "none"}, "порт 0"),
        ({"fs": "none", "network": {"hosts": ["h"], "ports": [70000]}, "process": "none"}, "порт вне диапазона"),
        ({"fs": {"mode": "read-write", "paths": ["rel/path"]}, "network": "none", "process": "none"}, "относительный путь"),
        ({"fs": {"mode": "read-write", "paths": []}, "network": "none", "process": "none"}, "пустой paths"),
        ({"fs": {"paths": ["/abs"]}, "network": "none", "process": "none"}, "скоуп без mode"),
        ({"fs": {"mode": "walrus", "paths": ["/abs"]}, "network": "none", "process": "none"}, "неизвестный режим"),
        ({"fs": {"mode": "read-write", "paths": ["/abs", ""]}, "network": "none", "process": "none"}, "пустой путь"),
    ],
)
def test_scoped_grammar_fail_closed(
    tmp_path: Path,
    journal: Journal,
    authority: dict[str, Any],
    почему: str,
) -> None:
    """Приёмка v0.5.0: неисполнимые скоупы — шлюз не стартует (fail-closed грамматика)."""
    with pytest.raises(GatewayConfigError):
        _gateway(tmp_path, journal, [_organ("bad", adapter="tests.fakes:FakeEcho", tools=["echo"], authority=authority)])
