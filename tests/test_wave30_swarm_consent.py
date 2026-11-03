"""Приёмка волны №30 — ТЗ-2.3: swarm-consent, согласие обеих сторон обмена (A21).

ТЗ-2.3 (docs/TZ.md, Ф-2): ADR по A2A-совместимости; consent обеих сторон,
manifest/provenance/freshness; после ADR — приёмки replay/revoked/poisoned.
Гейт: ADR принят → приёмки зелёные. Спека: SPEC-0002 v0.13.0 п.12, ADR-0017.

Дом обменивается с чужими агентами только по согласию ОБЕИХ сторон:
согласие дома — ``ConsentGrant`` (источник — Человек, granted_by), согласие
чужой стороны — её манифест (``PeerManifest``), дом не пишет за чужой дом.
Незаявленное не достраивается (A02), повтор ключа — записанный исход (A01),
окно свежести инъецируется часами (G2), отказ — поимённый и ДО факта обмена.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _consent():
    """Модуль загружается на каждый вызов: до кода волны — ModuleNotFoundError
    красит приёмку честно (красный прогон на нетронутом коде)."""
    return importlib.import_module("synapse.consent")


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def _grant(consent_mod, *, not_after: str, methods: tuple[str, ...] = ("summarize",), granted_by: str = "human", peer: str = "colleague-agent"):
    return consent_mod.ConsentGrant(
        consent_id="c-0001",
        peer=peer,
        methods=methods,
        granted_by=granted_by,
        not_after=not_after,
    )


def _peer(consent_mod, *, name: str = "colleague-agent", consents: bool = True):
    return consent_mod.PeerManifest(
        name=name,
        transport="stdio",
        consents=consents,
        provenance="peer-manifest@fingerprint-sha256:deadbeef",
    )


def _clock_at(now: datetime):
    return lambda: _iso(now)


# --- живое согласие обеих сторон ---


def test_both_sides_consent_grants_exchange() -> None:
    consent = _consent()
    reg = consent.ConsentRegistry(
        [_grant(consent, not_after=_iso(datetime(2026, 11, 4, tzinfo=timezone.utc)))],
        clock=_clock_at(datetime(2026, 11, 3, tzinfo=timezone.utc)),
    )
    verdict = reg.verify("ex-1", _peer(consent), "summarize")
    assert verdict.verdict == "granted"
    assert verdict.recorded is False  # первое решение


# --- поимённые отказы до факта ---


def test_unmanifested_peer_is_denied() -> None:
    consent = _consent()
    reg = consent.ConsentRegistry(
        [_grant(consent, not_after=_iso(datetime(2026, 11, 4, tzinfo=timezone.utc)))],
        clock=_clock_at(datetime(2026, 11, 3, tzinfo=timezone.utc)),
    )
    verdict = reg.verify("ex-2", _peer(consent, name="stranger"), "summarize")
    assert verdict.verdict == "denied"
    assert verdict.reason == "peer_unknown"


def test_silent_peer_is_denied() -> None:
    consent = _consent()
    reg = consent.ConsentRegistry(
        [_grant(consent, not_after=_iso(datetime(2026, 11, 4, tzinfo=timezone.utc)))],
        clock=_clock_at(datetime(2026, 11, 3, tzinfo=timezone.utc)),
    )
    verdict = reg.verify("ex-3", _peer(consent, consents=False), "summarize")
    assert verdict.verdict == "denied"
    assert verdict.reason == "peer_silent"


def test_method_out_of_scope_is_denied() -> None:
    consent = _consent()
    reg = consent.ConsentRegistry(
        [_grant(consent, not_after=_iso(datetime(2026, 11, 4, tzinfo=timezone.utc)))],
        clock=_clock_at(datetime(2026, 11, 3, tzinfo=timezone.utc)),
    )
    verdict = reg.verify("ex-4", _peer(consent), "delete_all")
    assert verdict.verdict == "denied"
    assert verdict.reason == "method_not_in_scope"


def test_expired_grant_is_denied_freshness() -> None:
    consent = _consent()
    reg = consent.ConsentRegistry(
        [_grant(consent, not_after=_iso(datetime(2026, 11, 2, tzinfo=timezone.utc)))],
        clock=_clock_at(datetime(2026, 11, 3, tzinfo=timezone.utc)),
    )
    verdict = reg.verify("ex-5", _peer(consent), "summarize")
    assert verdict.verdict == "denied"
    assert verdict.reason == "expired"


# --- отзыв: навсегда, будущее не оживляет прошлого ---


def test_revoked_consent_denies_new_exchange() -> None:
    consent = _consent()
    reg = consent.ConsentRegistry(
        [_grant(consent, not_after=_iso(datetime(2026, 11, 4, tzinfo=timezone.utc)))],
        clock=_clock_at(datetime(2026, 11, 3, tzinfo=timezone.utc)),
    )
    assert reg.verify("ex-6", _peer(consent), "summarize").verdict == "granted"
    reg.revoke("c-0001")
    verdict = reg.verify("ex-7", _peer(consent), "summarize")
    assert verdict.verdict == "denied"
    assert verdict.reason == "revoked"


def test_revoked_consent_id_cannot_be_reused() -> None:
    consent = _consent()
    reg = consent.ConsentRegistry(
        [_grant(consent, not_after=_iso(datetime(2026, 11, 4, tzinfo=timezone.utc)))],
        clock=_clock_at(datetime(2026, 11, 3, tzinfo=timezone.utc)),
    )
    reg.revoke("c-0001")
    with pytest.raises(ValueError, match="отозван"):
        reg.grant(_grant(consent, not_after=_iso(datetime(2026, 11, 4, tzinfo=timezone.utc))))


# --- повтор ключа — записанный исход (A01) ---


def test_replay_returns_recorded_verdict() -> None:
    consent = _consent()
    reg = consent.ConsentRegistry(
        [_grant(consent, not_after=_iso(datetime(2026, 11, 4, tzinfo=timezone.utc)))],
        clock=_clock_at(datetime(2026, 11, 3, tzinfo=timezone.utc)),
    )
    first = reg.verify("ex-8", _peer(consent), "summarize")
    second = reg.verify("ex-8", _peer(consent), "summarize")
    assert first.verdict == second.verdict == "granted"
    assert second.recorded is True  # повтор — записанный исход, решения нет
    assert reg.decisions == 1  # журнал решений не растёт
    # отзыв после записанного исхода не переписывает прошлое (кровь append-only),
    # но новый обмен уже не согласен
    reg.revoke("c-0001")
    third = reg.verify("ex-8", _peer(consent), "summarize")
    assert third.verdict == "granted" and third.recorded is True
    assert reg.verify("ex-9", _peer(consent), "summarize").reason == "revoked"


# --- отравленное согласие: fail-closed до факта (A02) ---


def test_poisoned_grammar_is_refused() -> None:
    consent = _consent()
    good = _iso(datetime(2026, 11, 4, tzinfo=timezone.utc))
    with pytest.raises(ValueError):  # незаявленный granted_by
        consent.ConsentGrant(
            consent_id="c-x", peer="p", methods=("m",), granted_by="anonymous", not_after=good
        )
    with pytest.raises(ValueError):  # не-ISO окно — нечитаемая свежесть
        consent.ConsentGrant(
            consent_id="c-x", peer="p", methods=("m",), granted_by="human", not_after="вчера"
        )
    with pytest.raises(ValueError):  # чужой ключ в данных согласия
        consent.ConsentGrant.from_dict(
            {
                "consent_id": "c-x",
                "peer": "p",
                "methods": ["m"],
                "granted_by": "human",
                "not_after": good,
                "signature": "forged",
            }
        )
    with pytest.raises(ValueError):  # незаявленный ключ в манифесте пира
        consent.PeerManifest.from_dict(
            {
                "name": "p",
                "transport": "stdio",
                "consents": True,
                "provenance": "peer-manifest@fingerprint-sha256:deadbeef",
                "admin": True,
            }
        )


def test_empty_methods_and_peer_refused() -> None:
    consent = _consent()
    good = _iso(datetime(2026, 11, 4, tzinfo=timezone.utc))
    with pytest.raises(ValueError):  # согласие на всё подряд — не согласие
        consent.ConsentGrant(consent_id="c-x", peer="p", methods=(), granted_by="human", not_after=good)
    with pytest.raises(ValueError):
        consent.ConsentGrant(consent_id="c-x", peer="", methods=("m",), granted_by="human", not_after=good)


# --- спека раньше кода, ADR принят ---


def test_spec_and_adr_live() -> None:
    spec = (REPO_ROOT / "specs" / "SPEC-0002-synapse-mcp.md").read_text(encoding="utf-8")
    assert "swarm-consent" in spec
    assert "согласие обеих сторон" in spec
    adr = (REPO_ROOT / "docs" / "adr" / "ADR-0017-swarm-consent.md").read_text(encoding="utf-8")
    assert "Статус: принято" in adr


def test_marker_lives_in_witness() -> None:
    witness = (REPO_ROOT / "synapse" / "consent.py").read_text(encoding="utf-8")
    assert "согласие обеих сторон" in witness
