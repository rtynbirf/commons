"""Общая оснастка тестов: временный манифест + шлюз + ствол мозга."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from blood.journal import Journal
from brainstem import Budget, Loop, Step
from synapse.gateway import Gateway

MANIFEST = {
    "version": "0.2.0",
    "updated": "2026-11-01",
    "transport_default": "stdio",
    "organs": [
        {
            "name": "sense-a",
            "system": "senses",
            "mode": "dependency",
            "upstream": "https://example.invalid/a",
            "license": "MIT",
            "transport": "stdio",
            "command": "fake-a",
            "healthcheck": "initialize handshake",
            "tools": ["echo"],
            "authority": {"fs": "read-only", "network": "none"},
            "adapter": "tests.fakes:FakeEcho",
        },
        {
            "name": "dead-b",
            "system": "senses",
            "mode": "dependency",
            "upstream": "https://example.invalid/b",
            "license": "MIT",
            "transport": "stdio",
            "command": "fake-b",
            "healthcheck": "initialize handshake",
            "tools": ["echo"],
            "authority": {"fs": "read-only", "network": "none"},
            "adapter": "tests.fakes:FakeDead",
        },
        {
            "name": "reserve-c",
            "system": "senses",
            "mode": "dependency",
            "upstream": "https://example.invalid/c",
            "license": "MIT",
            "transport": "stdio",
            "command": "fake-c",
            "healthcheck": "initialize handshake",
            "tools": ["echo"],
            "authority": {"fs": "read-only", "network": "none"},
            "adapter": "tests.fakes:FakeEcho",
        },
        {
            "name": "fallen-d",
            "system": "effectors",
            "mode": "dependency",
            "upstream": "https://example.invalid/d",
            "license": "MIT",
            "transport": "stdio",
            "command": "fake-d",
            "healthcheck": "initialize handshake",
            "tools": ["echo"],
            "authority": {"fs": "read-only", "network": "none"},
            "adapter": "tests.fakes:FakeFallen",
        },
        {
            "name": "abuser-e",
            "system": "effectors",
            "mode": "dependency",
            "upstream": "https://example.invalid/e",
            "license": "MIT",
            "transport": "stdio",
            "command": "fake-e",
            "healthcheck": "initialize handshake",
            "tools": ["escape"],
            "authority": {"fs": "read-only", "network": "none"},
            "adapter": "tests.fakes:FakeAbuser",
        },
    ],
    "substitutions": {"dead-b": ["reserve-c"]},
}


@pytest.fixture()
def manifest_path(tmp_path: Path) -> Path:
    path = tmp_path / "mcp-manifest.yaml"
    path.write_text(yaml.safe_dump(MANIFEST, allow_unicode=True), encoding="utf-8")
    return path


@pytest.fixture()
def journal() -> Journal:
    return Journal()


@pytest.fixture()
def gateway(manifest_path: Path, journal: Journal) -> Gateway:
    return Gateway(manifest_path, journal)


@pytest.fixture()
def loop(gateway: Gateway, journal: Journal) -> Loop:
    return Loop(gateway, journal)


def step(organ: str = "sense-a", tool: str = "echo", payload: dict | None = None, intent: str = "получить эхо") -> Step:
    return Step(organ=organ, tool=tool, payload=payload or {"data": "x"}, intent=intent)
