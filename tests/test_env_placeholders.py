"""Приёмка SPEC-0002 п.6: плейсхолдеры окружения в манифесте.

Открыто пульсом организма 2026-11-01: шлюз читал `${LLAMA_SERVER_URL}` как литерал
и не дошёл бы до метаболизма на реальной машине. Контракт: незаданная переменная —
«орган не развёрнут» (healthcheck ложь, вызов — отказной режим), шлюз живёт; заданная —
расширяется на старте.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from synapse.gateway import Gateway, OrganUnavailable


def write_manifest(tmp_path: Path, endpoint: str) -> Path:
    manifest = textwrap.dedent(f"""\
        organs:
          - name: remote-organ
            system: metabolism
            mode: dependency
            upstream: https://example.com/organ
            license: MIT
            transport: http
            endpoint: {endpoint}
            healthcheck: GET /health
            tools: [completion]
            authority: {{network: localhost, fs: none}}
          - name: local-organ
            system: senses
            mode: dependency
            upstream: https://example.com/local
            license: MIT
            transport: stdio
            command: local-organ-mcp
            healthcheck: initialize handshake
            tools: [convert]
            authority: {{fs: read-only, network: none}}
        substitutions:
          remote-organ: []
    """)
    path = tmp_path / "manifest.yaml"
    path.write_text(manifest, encoding="utf-8")
    return path


def test_unfilled_placeholder_keeps_gateway_alive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PULSE_METABOLISM_HOST", raising=False)
    gateway = Gateway(write_manifest(tmp_path, "${PULSE_METABOLISM_HOST}"))
    assert "remote-organ" in gateway.organ_names, "незаполненный плейсхолдер убил шлюз"
    assert gateway.health("remote-organ") is False, "неразвёрнутый орган не может быть здоров"
    with pytest.raises(OrganUnavailable):
        gateway.call("remote-organ", "completion", {}, trace_id="test")


def test_filled_placeholder_expands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PULSE_METABOLISM_HOST", "http://127.0.0.1:8080")
    gateway = Gateway(write_manifest(tmp_path, "${PULSE_METABOLISM_HOST}"))
    assert gateway.manifest_entry("remote-organ")["endpoint"] == "http://127.0.0.1:8080"


def test_real_manifest_deploys_only_configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Живой манифест репо: без переменных шлюз стартует, markitdown остаётся развёртываемым."""
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("LLAMA_SERVER_URL", raising=False)
    repo_manifest = Path(__file__).resolve().parent.parent / "synapse" / "mcp-manifest.yaml"
    gateway = Gateway(repo_manifest)
    assert gateway.health("ollama") is False and gateway.health("llama.cpp") is False
    assert "markitdown" in gateway.organ_names
