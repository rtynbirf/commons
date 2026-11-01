"""Смоук-тест боевого манифеста: манифест из репо обязан грузиться шлюзом."""

from __future__ import annotations

from pathlib import Path

from synapse.gateway import Gateway

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "synapse" / "mcp-manifest.yaml"


def test_real_manifest_loads_through_gateway() -> None:
    gateway = Gateway(MANIFEST)
    assert set(gateway.organ_names) == {"ollama", "llama.cpp", "markitdown", "browser-use", "openclaw"}


def test_every_manifest_organ_has_adapter() -> None:
    gateway = Gateway(MANIFEST)
    for name in gateway.organ_names:
        entry = gateway.manifest_entry(name)
        assert entry.get("adapter"), f"{name}: нет адаптера в манифесте"


def test_substitutions_reference_declared_organs_only() -> None:
    """SPEC-0002: замены ссылаются только на органы манифеста (иначе шлюз не стартует)."""
    gateway = Gateway(MANIFEST)  # загрузка сама валидирует таблицу замен
    assert "llama.cpp" in gateway.organ_names
