# Живой прогон волны №30 (swarm-consent: docs/TZ.md ТЗ-2.3, A21, SPEC-0002 п.12, ADR-0017).
# Дата: 2026-11-03. Красный прогон зафиксирован: 12 failed на нетронутом коде
# (ModuleNotFoundError synapse.consent; SPEC-0002 п.12 и ADR-0017 отсутствовали).
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, seal, verify  # noqa: E402
from synapse.consent import ConsentGrant, ConsentRegistry, PeerManifest  # noqa: E402

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
TRACE = "wave30-swarm-consent"

if JOURNAL.exists():
    raise SystemExit(
        "кровь прогона уже пролита и запечатана — прогон не переписывает свою кровь молча "
        "(косяк двойного запуска пойман живьём 2026-11-03: две печати одного файла); "
        "осознанный повтор — удалить blood.jsonl руками и назвав причину"
    )

journal = Journal()
journal.attach(JOURNAL)
results: dict[str, dict] = {}


def stamp(event_type: str, payload: dict, key: str) -> None:
    journal.append(make(event_type, "synapse", "self", TRACE, payload, Cost(0, 0, 0.0), idempotency_key=key))


NOW = "2026-11-03T14:00:00Z"
FUTURE = "2026-11-04T14:00:00Z"
PAST = "2026-11-02T14:00:00Z"

# --- ТЗ-2.3: согласие обеих сторон живьём --------------------------------------

grant = ConsentGrant(
    consent_id="c-2026-11-03-01",
    peer="colleague-agent",
    methods=("summarize", "read_digest"),
    granted_by="human",
    not_after=FUTURE,
)
peer = PeerManifest(
    name="colleague-agent",
    transport="stdio",
    consents=True,
    provenance="peer-manifest@fingerprint-sha256:live-probe-2026-11-03",
)
reg = ConsentRegistry([grant], clock=lambda: NOW)

# granted: обе стороны согласны, метод в белом списке, окно живо
v = reg.verify("ex-01", peer, "summarize")
assert v.ok and not v.recorded
results["granted"] = {"verdict": v.verdict, "reason": v.reason}
stamp("act", {"consent": {"exchange": "ex-01", "method": "summarize", "verdict": v.verdict, "reason": v.reason, "recorded": v.recorded}}, "wave30-ex-01")

# A01: повтор ключа обмена — записанный исход, журнал решений не растёт
v2 = reg.verify("ex-01", peer, "summarize")
assert v2.ok and v2.recorded and reg.decisions == 1
results["replay"] = {"verdict": v2.verdict, "recorded": v2.recorded, "decisions": reg.decisions}
stamp("act", {"consent": {"exchange": "ex-01-repeat", "verdict": v2.verdict, "reason": v2.reason, "recorded": v2.recorded, "decisions": reg.decisions}}, "wave30-ex-01-repeat")

# peer_silent: согласия второй стороны нет — обмен не начинается
silent = PeerManifest(
    name="colleague-agent",
    transport="stdio",
    consents=False,
    provenance="peer-manifest@fingerprint-sha256:live-probe-2026-11-03",
)
v3 = reg.verify("ex-03", silent, "summarize")
assert not v3.ok and v3.reason == "peer_silent"
results["peer_silent"] = {"reason": v3.reason}
stamp("error", {"consent": {"exchange": "ex-03", "verdict": v3.verdict, "reason": v3.reason, "honesty": "обмен не начался — согласия второй стороны нет (A21)"}}, "wave30-ex-03")

# peer_unknown: согласия дома чужому дому нет
stranger = PeerManifest(
    name="stranger-agent",
    transport="stdio",
    consents=True,
    provenance="peer-manifest@fingerprint-sha256:unmet",
)
v4 = reg.verify("ex-04", stranger, "summarize")
assert not v4.ok and v4.reason == "peer_unknown"
results["peer_unknown"] = {"reason": v4.reason}
stamp("error", {"consent": {"exchange": "ex-04", "verdict": v4.verdict, "reason": v4.reason, "honesty": "согласия дома чужому дому нет"}}, "wave30-ex-04")

# method_not_in_scope: белый список не пуст — «согласие на всё подряд» не согласие
v5 = reg.verify("ex-05", peer, "delete_all")
assert not v5.ok and v5.reason == "method_not_in_scope"
results["method_not_in_scope"] = {"reason": v5.reason}
stamp("error", {"consent": {"exchange": "ex-05", "verdict": v5.verdict, "reason": v5.reason, "honesty": "метод вне белого списка согласия"}}, "wave30-ex-05")

# expired: окно свежести вышло (freshness, время инъецировано — G2)
expired = ConsentGrant(
    consent_id="c-2026-11-03-02",
    peer="old-colleague",
    methods=("summarize",),
    granted_by="human",
    not_after=PAST,
)
reg_expired = ConsentRegistry([expired], clock=lambda: NOW)
v6 = reg_expired.verify(
    "ex-06",
    PeerManifest(name="old-colleague", transport="stdio", consents=True, provenance="peer-manifest@archive"),
    "summarize",
)
assert not v6.ok and v6.reason == "expired"
results["expired"] = {"reason": v6.reason}
stamp("error", {"consent": {"exchange": "ex-06", "verdict": v6.verdict, "reason": v6.reason, "honesty": "окно свежести вышло — согласие устарело"}}, "wave30-ex-06")

# revoked: отзыв действует на будущее; записанный исход не переписывается
v7 = reg.verify("ex-07", peer, "read_digest")
assert v7.ok
reg.revoke("c-2026-11-03-01")
v8 = reg.verify("ex-08", peer, "read_digest")
assert not v8.ok and v8.reason == "revoked"
v7b = reg.verify("ex-07", peer, "read_digest")
assert v7b.ok and v7b.recorded, "отзыв не переписывает записанный исход (A01, кровь append-only)"
results["revoked"] = {"future": v8.reason, "recorded_kept": v7b.verdict}
stamp("error", {"consent": {"exchange": "ex-08", "verdict": v8.verdict, "reason": v8.reason, "honesty": "отзыв действует на будущее; записанный исход ex-07 не переписан (A01, кровь append-only)"}}, "wave30-ex-08")

# poisoned: отравленная грамматика согласия — отказ до факта (A02)
poison_caught = 0
try:
    ConsentGrant.from_dict(
        {"consent_id": "c-x", "peer": "p", "methods": ["m"], "granted_by": "human", "not_after": FUTURE, "signature": "forged"}
    )
except ValueError:
    poison_caught += 1
try:
    ConsentGrant(consent_id="c-y", peer="p", methods=("m",), granted_by="anonymous", not_after=FUTURE)
except ValueError:
    poison_caught += 1
try:
    ConsentGrant(consent_id="c-z", peer="p", methods=("m",), granted_by="human", not_after="вчера")
except ValueError:
    poison_caught += 1
try:
    reg.grant(
        ConsentGrant(consent_id="c-2026-11-03-01", peer="colleague-agent", methods=("summarize",), granted_by="human", not_after=FUTURE)
    )
except ValueError:
    poison_caught += 1
assert poison_caught == 4, poison_caught
results["poisoned"] = {"caught": poison_caught}
stamp("error", {"consent": {"exchange": "ex-09", "verdict": "denied", "reason": "poisoned", "caught": poison_caught, "honesty": "отравленное согласие не исполняется: чужой ключ, незаявленный источник, нечитаемое окно, оживление отозванного — все пойманы до факта (A02)"}}, "wave30-ex-09")

# --- финал -----------------------------------------------------------------------

journal.append(
    make(
        "reflect",
        "synapse",
        "self",
        TRACE,
        {
            "verdict": "ТЗ-2.3 swarm-consent (A21 СЛУЖЕНО, SPEC-0002 v0.13.0 п.12, ADR-0017) служен замером: согласие обеих сторон — поимённый вердикт до факта; повтор ключа — записанный исход (A01); отзыв действует на будущее, записанное не переписывает; отравленная грамматика — отказ до факта (A02)",
            "honesty": "peer_silent пойман живьём: согласие второй стороны — её голос, дом не пишет за чужой дом",
            "next": "ТЗ-2.6 (за Человеком), ТЗ-3.2 (за Человеком), ТЗ-3.4 (за Человеком), донорский трек",
        },
        Cost(0, 0, 0.0),
        idempotency_key="wave30-reflect",
    )
)

journal.close()
report = verify(JOURNAL)
print(json.dumps(report, ensure_ascii=False))
assert report["gaps"] == [] and not report.get("content_gaps")

rel = str(JOURNAL.relative_to(REPO_ROOT))
anchor = seal(JOURNAL, name=rel)
anchors_path = REPO_ROOT / "blood" / "anchors.jsonl"
existing = [json.loads(l) for l in anchors_path.read_text(encoding="utf-8").splitlines() if l.strip()]
if not any(r.get("file") == rel and r.get("last_sha256") == anchor["last_sha256"] for r in existing):
    with anchors_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(anchor, ensure_ascii=False) + "\n")
    print("якорь опечатан")
else:
    print("якорь того же состояния уже в книге")

print("ИТОГ ВОЛНЫ №30:", json.dumps(results, ensure_ascii=False, indent=2))
