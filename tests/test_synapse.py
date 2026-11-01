"""Приёмка SPEC-0002: шлюз синапсов — veto, замены, полномочия, манифест."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from blood.journal import Journal
from synapse.gateway import (
    AuthorityViolation,
    Gateway,
    GatewayConfigError,
    OrganUnavailable,
    SynapseVeto,
)

from .conftest import MANIFEST  # noqa: TID252 — тестовый артефакт проекта


def test_veto_on_unannounced_organ(gateway: Gateway, journal: Journal) -> None:
    with pytest.raises(SynapseVeto):
        gateway.call("unknown-organ", "echo", {}, "trace1")
    (veto,) = journal.by_type("veto")
    assert veto["organ"] == "unknown-organ"
    assert veto["source"] == "synapse"


def test_veto_on_unannounced_tool(gateway: Gateway, journal: Journal) -> None:
    with pytest.raises(SynapseVeto):
        gateway.call("sense-a", "delete_everything", {}, "trace2")
    (veto,) = journal.by_type("veto")
    assert veto["payload"]["tool"] == "delete_everything"


def test_dead_organ_routes_to_substitute(gateway: Gateway, journal: Journal) -> None:
    """Тест отключения: dead-b молчит — трафик уходит к reserve-c без правки кода."""
    result = gateway.call("dead-b", "echo", {"data": "42"}, "trace3")
    assert result["echo"] == {"data": "42"}
    (replacement,) = journal.by_type("organ.replace")
    assert replacement["payload"] == {"from": "dead-b", "to": "reserve-c"}


def test_organ_without_substitutes_raises_unavailable(gateway: Gateway) -> None:
    with pytest.raises(OrganUnavailable):
        gateway.call("fallen-d", "echo", {}, "trace4")


def test_authority_violation_is_recorded(gateway: Gateway, journal: Journal) -> None:
    with pytest.raises(AuthorityViolation):
        gateway.call("abuser-e", "escape", {}, "trace5")
    (violation,) = journal.by_type("security.violation")
    assert violation["organ"] == "abuser-e"


def test_every_call_carries_cost(gateway: Gateway, journal: Journal) -> None:
    gateway.call("sense-a", "echo", {"data": "7"}, "trace6")
    (act,) = journal.by_type("act")
    assert act["cost"]["tokens_in"] > 0 and act["cost"]["seconds"] >= 0.01


def test_duplicate_names_rejected(tmp_path: Path) -> None:
    manifest = {"organs": [MANIFEST["organs"][0], MANIFEST["organs"][0]], "substitutions": {}}
    path = tmp_path / "m.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    with pytest.raises(GatewayConfigError):
        Gateway(path)


def test_stdio_without_command_rejected(tmp_path: Path) -> None:
    broken = dict(MANIFEST["organs"][0])
    del broken["command"]
    manifest = {"organs": [broken], "substitutions": {}}
    path = tmp_path / "m.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    with pytest.raises(GatewayConfigError):
        Gateway(path)


def test_substitution_to_unknown_organ_rejected(tmp_path: Path) -> None:
    manifest = {"organs": [MANIFEST["organs"][0]], "substitutions": {"sense-a": ["ghost"]}}
    path = tmp_path / "m.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    with pytest.raises(GatewayConfigError):
        Gateway(path)


def test_new_organ_via_manifest_only(tmp_path: Path, journal: Journal) -> None:
    """Приёмка SPEC-0002: орган добавляется правкой манифеста — код шлюза не трогаем."""
    new_organ = {
        "name": "late-organ",
        "system": "senses",
        "mode": "dependency",
        "upstream": "https://example.invalid/late",
        "license": "MIT",
        "transport": "stdio",
        "command": "fake-late",
        "healthcheck": "initialize handshake",
        "tools": ["echo"],
        "authority": {"fs": "none", "network": "none"},
        "adapter": "tests.fakes:FakeEcho",
    }
    manifest = {"organs": MANIFEST["organs"] + [new_organ], "substitutions": {}}
    path = tmp_path / "m.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    gateway = Gateway(path, journal)
    result = gateway.call("late-organ", "echo", {"data": "ok"}, "trace7")
    assert result["echo"] == {"data": "ok"}
