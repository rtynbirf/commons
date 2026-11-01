"""Приёмки донорского протокола (SPEC-0008, ADR-0010).

Тело дарит кровь только по рукопожатию (DCO) и тому, кто дарит. Ошейник (CLA)
не подписывается; непотипированный орган не получает донорства; карта без
доказательств — не карта. Гейт — fail-closed, итог машина-читаем:
`TRANSPLANT: N ok, M failed`.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

import immune.donation as donation

REPO_ROOT = Path(__file__).resolve().parent.parent
DONATION = REPO_ROOT / "organs" / "donation.yaml"
REGISTRY = REPO_ROOT / "organs" / "registry.yaml"
MATRIX = REPO_ROOT / "immune" / "license-matrix.yaml"
SPEC = REPO_ROOT / "specs" / "SPEC-0008-transplant.md"

EVIDENCE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SPEC_BULLET = re.compile(r"^[ \t]*- `([^`]+)` — ", re.M)


def _cards() -> list[dict]:
    data = yaml.safe_load(DONATION.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and isinstance(data.get("cards"), list), "карты повреждены"
    return data["cards"]


def _registry() -> dict:
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))


def _registry_entries() -> dict[str, dict]:
    return donation.load_registry_entries_from(_registry())


def _matrix() -> dict:
    return yaml.safe_load(MATRIX.read_text(encoding="utf-8"))


def _card(repo: str) -> dict:
    for card in _cards():
        if card.get("repo") == repo:
            return card
    raise AssertionError(f"карта {repo} отсутствует")


# --- Живое тело проходит гейт -------------------------------------------------


def test_live_cards_pass_the_gate() -> None:
    """Живые карты: гейт зелёный, каждый вердикт печатается, итог машина-читаем."""
    out = subprocess.run(
        [sys.executable, "-m", "immune.donation"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, f"гейт красный:\n{out.stdout}\n{out.stderr}"
    lines = out.stdout.strip().splitlines()
    for card in _cards():
        assert any(l.startswith(f"OK {card['repo']} ") for l in lines), f"нет вердикта OK для {card['repo']}"
    assert lines[-1].startswith("TRANSPLANT: "), "итог гейта не машина-читаем"
    assert lines[-1] == f"TRANSPLANT: {len(_cards())} ok, 0 failed", f"итог неожидан: {lines[-1]}"


def test_gate_is_fail_closed_on_broken_data(tmp_path: Path) -> None:
    """Повреждённый YAML карт — отказ гейта, молчаливого пропуска нет (G1)."""
    broken = tmp_path / "broken.yaml"
    broken.write_text("cards: [ { repo: ollama/ollama\n", encoding="utf-8")
    out = subprocess.run(
        [sys.executable, "-m", "immune.donation", "--donation", str(broken)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 1
    assert "TRANSPLANT: FAIL" in out.stdout or "TRANSPLANT: FAIL" in out.stderr


# --- Карты ссылаются только на органы тела ------------------------------------


def test_every_card_organ_exists_in_registry() -> None:
    """Кровь отдаётся только органам тела: repo карты есть в живом реестре."""
    entries = _registry_entries()
    for card in _cards():
        assert card["repo"] in entries, f"орган {card['repo']} не в реестре"


def test_consume_only_matches_external_modes() -> None:
    """consume-only согласован с реестром: орган не в core_modes (внешний узел)."""
    core = {"dependency", "adapter"}
    for card in _cards():
        if card.get("decision") != "consume-only":
            continue
        mode = _registry_entries()[card["repo"]].get("mode")
        assert mode not in core, f"{card['repo']}: consume-only при core-режиме '{mode}'"


# --- Аксиома: ошейник не подписывается -----------------------------------------


def test_collar_organs_do_not_donate() -> None:
    """cla-органы не имеют donate."""
    for repo in ("react/react", "n8n-io/n8n"):
        card = _card(repo)
        assert card["protocol"] == "cla", f"{repo}: ожидается ошейник cla"
        assert card["decision"] != "donate", f"{repo}: кровь не подписывает CLA"


def test_react_patch_stays_inside() -> None:
    """MIT-лицензия кожи не делает тело донором: react — patch-inside."""
    assert _card("react/react")["decision"] == "patch-inside"


def test_n8n_is_consume_only() -> None:
    """fair-code + CLA — двойная несовместимость: n8n — consume-only."""
    assert _card("n8n-io/n8n")["decision"] == "consume-only"


def test_untyped_organ_does_not_donate() -> None:
    """Непотипированный орган не получает донорства."""
    card = _card("ggml-org/llama.cpp")
    assert card["protocol"] == "unverified"
    assert card["decision"] != "donate"


def test_donating_organs_are_collarless_and_mutual() -> None:
    """donate только у органов без ошейников, чья лицензия проходит входную матрицу."""
    allowed = {str(item) for item in _matrix()["allowed"]}
    entries = _registry_entries()
    for card in _cards():
        if card.get("decision") != "donate":
            continue
        assert card["protocol"] in ("dco", "none-observed"), f"{card['repo']}: donate при протоколе '{card['protocol']}'"
        license_ = str(entries[card["repo"]].get("license_pre", ""))
        assert license_ in allowed, f"{card['repo']}: дарим тому, кто дарит, а '{license_}' вне allowed"


# --- Evidence: карта без доказательств — не карта -------------------------------


def test_every_card_has_dated_evidence() -> None:
    """У каждой карты есть evidence: дата YYYY-MM-DD, https-URL, непустой факт."""
    for card in _cards():
        evidence = card.get("evidence")
        assert isinstance(evidence, list) and evidence, f"{card['repo']}: evidence отсутствует"
        for i, item in enumerate(evidence, start=1):
            assert isinstance(item, dict), f"{card['repo']}: evidence[{i}] не словарь"
            assert EVIDENCE_DATE.match(str(item.get("date", ""))), f"{card['repo']}: evidence[{i}] без даты"
            assert str(item.get("url", "")).startswith("https://"), f"{card['repo']}: evidence[{i}] без https-URL"
            assert str(item.get("fact", "")).strip(), f"{card['repo']}: evidence[{i}] без факта"


# --- G2: данные, не код ----------------------------------------------------------


def _tmp_donation(tmp_path: Path, cards: list[dict]) -> Path:
    p = tmp_path / "donation-tmp.yaml"
    p.write_text(yaml.safe_dump({"cards": cards}, allow_unicode=True), encoding="utf-8")
    return p


def _run_gate(tmp_path: Path, cards: list[dict]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "immune.donation", "--donation", str(_tmp_donation(tmp_path, cards))],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_g2_protocol_swap_changes_verdict_without_code(tmp_path: Path) -> None:
    """Смена протокола в данных меняет вердикт без правки кода (G2): в обе стороны."""
    cards = yaml.safe_load(DONATION.read_text(encoding="utf-8"))["cards"]

    # 1) ошейник сняли в данных -> donate становится возможен (лицензия MIT в allowed).
    swapped = yaml.safe_load(yaml.safe_dump(cards))
    for card in swapped:
        if card["repo"] == "react/react":
            card["protocol"] = "dco"
            card["decision"] = "donate"
    proc = _run_gate(tmp_path, swapped)
    assert proc.returncode == 0, f"гейт красный после снятия ошейника:\n{proc.stdout}"
    assert "OK react/react dco donate" in proc.stdout

    # 2) ошейник надели в данных -> донорство запрещено ('collar').
    collared = yaml.safe_load(yaml.safe_dump(cards))
    for card in collared:
        if card["repo"] == "ollama/ollama":
            card["protocol"] = "cla"
    proc = _run_gate(tmp_path, collared)
    assert proc.returncode == 1
    assert "FAIL ollama/ollama cla donate (collar)" in proc.stdout


# --- Отказные режимы -------------------------------------------------------------


def _minimal_card(repo: str) -> dict:
    return {
        "repo": repo,
        "protocol": "dco",
        "decision": "donate",
        "evidence": [{"date": "2026-11-02", "url": "https://example.org/x", "fact": "проверено"}],
    }


def test_g1_card_without_fields_fails_closed(tmp_path: Path) -> None:
    """Карта без protocol/decision — отказ 'missing', не пропуск (G1)."""
    proc = _run_gate(tmp_path, [{"repo": "ollama/ollama"}])
    assert proc.returncode == 1
    assert "(missing)" in proc.stdout


def test_g1_card_without_evidence_fails_closed(tmp_path: Path) -> None:
    """Карта без evidence — отказ: карта без доказательств — не карта."""
    card = _minimal_card("ollama/ollama")
    card["evidence"] = []
    proc = _run_gate(tmp_path, [card])
    assert proc.returncode == 1
    assert "(missing)" in proc.stdout


def test_unknown_organ_fails(tmp_path: Path) -> None:
    """Карта на орган вне живого реестра — отказ 'unknown-organ'."""
    proc = _run_gate(tmp_path, [_minimal_card("someone/unknown-organ")])
    assert proc.returncode == 1
    assert "(unknown-organ)" in proc.stdout


def test_duplicate_card_fails(tmp_path: Path) -> None:
    """Дубликат карты — отказ 'duplicate'."""
    proc = _run_gate(tmp_path, [_minimal_card("ollama/ollama"), _minimal_card("ollama/ollama")])
    assert proc.returncode == 1
    assert "(duplicate)" in proc.stdout


def test_not_mutual_fails(tmp_path: Path) -> None:
    """Дарим тому, кто дарит: donate органу с AGPL (вне allowed) — отказ 'not-mutual'."""
    proc = _run_gate(tmp_path, [_minimal_card("firecrawl/firecrawl")])
    assert proc.returncode == 1
    assert "(not-mutual)" in proc.stdout


def test_bad_evidence_entries_fail(tmp_path: Path) -> None:
    """evidence без даты / с http (не https) / с пустым фактом — отказ."""
    base = _minimal_card("ollama/ollama")
    for broken in (
        {"date": "завтра", "url": "https://example.org", "fact": "x"},
        {"date": "2026-11-02", "url": "http://example.org", "fact": "x"},
        {"date": "2026-11-02", "url": "https://example.org", "fact": "  "},
    ):
        card = yaml.safe_load(yaml.safe_dump(base))
        card["evidence"] = [broken]
        proc = _run_gate(tmp_path, [card])
        assert proc.returncode == 1, f"evidence {broken} прошёл гейт"
        assert "(missing)" in proc.stdout


# --- Спека сдаёт свою кровь: дрейф спека<->данные<->код невозможен ----------------


def test_spec_enums_match_data_and_code() -> None:
    """Словари протоколов и решений SPEC-0008 == данные карт == механизм."""
    text = SPEC.read_text(encoding="utf-8")
    contract = text.split("## Контракт", 1)[1].split("## Гарантии", 1)[0]
    bullets = SPEC_BULLET.findall(contract)
    spec_protocols = {b for b in bullets if b in donation.PROTOCOLS or b in ("dco", "none-observed", "cla", "unverified")}
    spec_decisions = {b for b in bullets if b in donation.DECISIONS}
    assert spec_protocols == set(donation.PROTOCOLS), f"спека vs код (протоколы): {spec_protocols} vs {set(donation.PROTOCOLS)}"
    assert spec_decisions == set(donation.DECISIONS), f"спека vs код (решения): {spec_decisions} vs {set(donation.DECISIONS)}"

    data = yaml.safe_load(DONATION.read_text(encoding="utf-8"))
    assert set(data["protocols"]) == set(donation.PROTOCOLS), "данные vs код (протоколы)"
    assert set(data["decisions"]) == set(donation.DECISIONS), "данные vs код (решения)"
