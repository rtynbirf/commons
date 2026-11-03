"""Swarm-consent — согласие обеих сторон обмена (ТЗ-2.3, A21, SPEC-0002 п.12, ADR-0017).

Дом обменивается с чужим агентом только по согласию ОБЕИХ сторон, названному
ДО факта обмена. Согласие дома — ``ConsentGrant`` (источник — Человек, PID 1,
``granted_by``); согласие второй стороны — её ``PeerManifest`` (дом не пишет
за чужой дом). Вердикт — поимённый: ``granted`` либо ``denied`` с причиной
(``peer_unknown`` | ``peer_silent`` | ``method_not_in_scope`` | ``revoked`` |
``expired``). Незаявленное не достраивается (A02): отравленная грамматика
согласия — ``ValueError`` до факта. Повтор ключа обмена — записанный исход
(A01), журнал решений не растёт. Отзыв действует на будущее и не переписывает
записанные исходы (кровь append-only); отозванный ``consent_id`` не оживает
повторным grant. Время инъецируется (G2) — часы аргумент реестра.

Consent — предикат, не транспорт и не шина: ничего не доставляет (кровь —
журнал фактов, ADR-001; транспорт — ADR-0016), живёт в синапсах рядом со
стражем полномочий: страж отвечает «можно ли этому органу», consent —
«хотят ли обе стороны».
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any, Callable, Iterable

__all__ = [
    "ConsentGrant",
    "PeerManifest",
    "ConsentVerdict",
    "ConsentRegistry",
]

# Заявленные ярлыки источника согласия дома: Человек (PID 1) или орган по
# его поручению. Незаявленное не достраивается (A02).
GRANTED_BY = ("human", "organ")

# Словарь транспортов дома (ADR-0016): локальный транспорт, наружного шлюза нет.
TRANSPORTS = ("stdio", "http-localhost", "none")

_GRANT_KEYS = {"consent_id", "peer", "methods", "granted_by", "not_after"}
_PEER_KEYS = {"name", "transport", "consents", "provenance"}


def _parse_moment(value: str) -> datetime:
    """Нечитаемое окно свежести — отравленное согласие (A02, fail-closed)."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("consent: not_after пуст — нечитаемая свежесть не согласие")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"consent: not_after {value!r} не ISO-8601 — окно нечитаемо") from exc


def _freeze_data(cls: type, data: dict[str, Any], allowed: set[str], label: str):
    """Строгий конструктор из данных: незаявленный ключ — ValueError (A02)."""
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"{label}: незаявленные ключи {sorted(unknown)} — незаявленное не достраивается (A02)")
    missing = allowed - set(data)
    if missing:
        raise ValueError(f"{label}: не хватает ключей {sorted(missing)} — согласие неполно")
    names = [f.name for f in fields(cls)]
    return cls(**{k: data[k] for k in names})


@dataclass(frozen=True)
class ConsentGrant:
    """Согласие дома на обмен с чужим агентом (источник — Человек, PID 1)."""

    consent_id: str
    peer: str
    methods: tuple[str, ...]
    granted_by: str
    not_after: str

    def __post_init__(self) -> None:
        if not self.consent_id or not isinstance(self.consent_id, str):
            raise ValueError("consent: consent_id пуст — согласие без ключа не живёт")
        if not self.peer or not isinstance(self.peer, str):
            raise ValueError("consent: peer пуст — согласие «с кем-то» не согласие")
        if (
            not isinstance(self.methods, tuple)
            or not self.methods
            or not all(isinstance(m, str) and m for m in self.methods)
        ):
            raise ValueError("consent: methods пуст или не список строк — согласие на всё подряд не согласие")
        if self.granted_by not in GRANTED_BY:
            raise ValueError(
                f"consent: granted_by {self.granted_by!r} не из {GRANTED_BY} — незаявленный источник не достраивается (A02)"
            )
        _parse_moment(self.not_after)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConsentGrant":
        return _freeze_data(cls, dict(data), _GRANT_KEYS, "consent grant")


@dataclass(frozen=True)
class PeerManifest:
    """Объявление второй стороны (её голос): дом читает, но не порождает."""

    name: str
    transport: str
    consents: bool
    provenance: str

    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.name, str):
            raise ValueError("consent: манифест пира без имени — обмен с безымянным не начинается")
        if self.transport not in TRANSPORTS:
            raise ValueError(
                f"consent: транспорт {self.transport!r} не из {TRANSPORTS} (ADR-0016) — незаявленное не достраивается (A02)"
            )
        if not isinstance(self.consents, bool):
            raise ValueError("consent: consents не bool — чужое слово не фантазируем (A02)")
        if not self.provenance or not isinstance(self.provenance, str):
            raise ValueError("consent: provenance пуст — неизвестно, откуда знаем о пире (A02)")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PeerManifest":
        return _freeze_data(cls, dict(data), _PEER_KEYS, "peer manifest")


@dataclass(frozen=True)
class ConsentVerdict:
    """Поимённый вердикт согласия ДО факта обмена."""

    verdict: str  # "granted" | "denied"
    reason: str  # "both_sides_consent" | "peer_unknown" | ... | ""
    recorded: bool  # A01: True — записанный исход, решения не было

    @property
    def ok(self) -> bool:
        return self.verdict == "granted"


@dataclass
class ConsentRegistry:
    """Реестр согласий дома: verify решает ДО факта, повтор ключа — записанный исход."""

    grants: Iterable[ConsentGrant | dict[str, Any]]
    clock: Callable[[], str] = field(repr=False)

    def __post_init__(self) -> None:
        self._grants: dict[str, ConsentGrant] = {}
        self._revoked: set[str] = set()
        self._decisions: dict[str, ConsentVerdict] = {}
        for raw in self.grants:
            self.grant(raw)

    # --- согласие дома ---

    def grant(self, item: ConsentGrant | dict[str, Any]) -> ConsentGrant:
        row = item if isinstance(item, ConsentGrant) else ConsentGrant.from_dict(item)
        if row.consent_id in self._revoked:
            raise ValueError(
                f"consent: {row.consent_id} отозван — отозванное согласие не оживает, новый обмен требует нового consent_id"
            )
        if row.consent_id in self._grants:
            raise ValueError(f"consent: {row.consent_id} уже жив — согласие с тем же ключом не дублируется")
        self._grants[row.peer] = row
        return row

    def revoke(self, consent_id: str) -> None:
        known = any(g.consent_id == consent_id for g in self._grants.values())
        if not known and consent_id not in self._revoked:
            raise ValueError(f"consent: {consent_id} не жив — отзывать нечего (незаявленное не фантазируем)")
        self._revoked.add(consent_id)

    # --- вердикт ДО факта ---

    def verify(self, exchange_key: str, peer: PeerManifest, method: str) -> ConsentVerdict:
        recorded = self._decisions.get(exchange_key)
        if recorded is not None:
            return ConsentVerdict(recorded.verdict, recorded.reason, True)  # A01: записанный исход
        verdict = self._decide(peer, method)
        self._decisions[exchange_key] = verdict
        return verdict

    def _decide(self, peer: PeerManifest, method: str) -> ConsentVerdict:
        grant = self._grants.get(peer.name)
        if grant is None:
            return ConsentVerdict("denied", "peer_unknown", False)
        if not peer.consents:
            return ConsentVerdict("denied", "peer_silent", False)  # согласия второй стороны нет
        if method not in grant.methods:
            return ConsentVerdict("denied", "method_not_in_scope", False)
        if grant.consent_id in self._revoked:
            return ConsentVerdict("denied", "revoked", False)
        now = _parse_moment(self.clock())
        if now > _parse_moment(grant.not_after):
            return ConsentVerdict("denied", "expired", False)
        return ConsentVerdict("granted", "both_sides_consent", False)

    @property
    def decisions(self) -> int:
        """Число принятых решений: повтор ключа его не растит (A01)."""
        return len(self._decisions)
