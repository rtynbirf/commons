"""Приёмка реестра пиров — голос роя cell-swarm читается грамматикой дома.

Основание: ADR-0017 (swarm-consent: согласие обеих сторон), предложение
ADR-0019 (черновик: synapse/peers/*.yaml — где дом хранит прочитанные голоса).
Гейт: черновик ADR принят Человеком → приёмка зелёная; незаявленное в голосе
пира краснит (A02, fail-closed). Спека: SPEC-0002 п.12 (v0.13.0).

Дом не пишет за чужой дом: файл в synapse/peers/ — голос второй стороны,
привезённый провенансом; приёмка только читает и типирует.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PEERS_DIR = REPO_ROOT / "synapse" / "peers"


def _consent():
    return importlib.import_module("synapse.consent")


def _peer_files() -> list[Path]:
    if not PEERS_DIR.exists():
        pytest.skip("synapse/peers/ ещё не заведён — черновик ADR-0019 не принят")
    files = sorted(PEERS_DIR.glob("*.yaml"))
    assert files, "реестр пиров пуст — каталог есть, голосов нет"
    return files


def test_every_peer_manifest_is_house_grammar_valid():
    """Каждый голос в synapse/peers/ строится PeerManifest дома без ValueError."""
    consent = _consent()
    for path in _peer_files():
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        peer = consent.PeerManifest.from_dict(data)  # незаявленное — ValueError (A02)
        assert peer.name == path.stem, f"{path.name}: имя файла = имя пира"
        assert peer.consents is True, f"{path.name}: пир в реестре с consents=false — молчаливого пира не держим"


def test_cell_swarm_voice():
    """Живой пир роя: имя, локальный транспорт (ADR-0016), провенанс с датой."""
    consent = _consent()
    path = PEERS_DIR / "cell-swarm.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    peer = consent.PeerManifest.from_dict(data)
    assert peer.name == "cell-swarm"
    assert peer.transport in ("stdio", "http-localhost"), "наружный транспорт у пира — нарушение ADR-0016"
    assert "2026-11-05" in peer.provenance, "провенанс голоса без даты — откуда дом знает о пире"


def test_poisoned_peer_manifest_red():
    """Отравленный голос краснит: незаявленный ключ и незаявленный транспорт."""
    consent = _consent()
    with pytest.raises(ValueError):
        consent.PeerManifest.from_dict(
            {"name": "x", "transport": "stdio", "consents": True, "provenance": "p", "url": "лишний ключ"}
        )
    with pytest.raises(ValueError):
        consent.PeerManifest.from_dict({"name": "x", "transport": "wifi", "consents": True, "provenance": "p"})


def test_peer_is_not_an_organ():
    """Пир не орган: имени пира нет в реестре органов — смешение ролей краснит."""
    registry = yaml.safe_load((REPO_ROOT / "organs" / "registry.yaml").read_text(encoding="utf-8"))
    organ_repos = {organ.get("repo", "") for organ in registry.get("organs", [])}
    for path in _peer_files():
        assert f"rtynbirf/{path.stem}" not in organ_repos or path.stem == "commons", \
            f"{path.stem}: пир одновременно вписан органом — роли смешаны"
