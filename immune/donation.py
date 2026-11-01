# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Донорский протокол COMMONS (SPEC-0009, ADR-0011): карта -> вердикт.

Трансплантология — исходящий иммунитет: куда тело отдаёт свою кровь. Данные —
organs/donation.yaml (карты донорства с evidence и датой); этот модуль — только
механизм применения. Fail-closed (G1): карты нет или она неполна — донорства нет.

Аксиома: тело дарит кровь только по рукопожатию (DCO) и тому, кто дарит.
CLA — ошейник: права на кровь переходят хозяину репозитория. Ошейник не
подписывается; патч живёт внутри организма.
"""
from __future__ import annotations

import argparse
import datetime
import pathlib
import sys
from dataclasses import dataclass

import yaml

DONATION_PATH = pathlib.Path(__file__).resolve().parent.parent / "organs" / "donation.yaml"
REGISTRY_PATH = pathlib.Path(__file__).resolve().parent.parent / "organs" / "registry.yaml"
MATRIX_PATH = pathlib.Path(__file__).with_name("license-matrix.yaml")

PROTOCOLS = ("dco", "none-observed", "cla", "unverified")
DECISIONS = ("donate", "patch-inside", "consume-only")

# sys.stdout на момент импорта — фактический объект-дефолт параметра out
# (см. run_check: дефолт пере-разрешается в момент вызова).
_IMPORT_STDOUT = sys.stdout


@dataclass(frozen=True)
class Decision:
    """Вердикт донорского протокола по одной карте."""

    ok: bool
    organ: str
    protocol: str
    decision: str
    rule: str     # donate/patch-inside/consume-only/collar/untyped/not-mutual/unknown-organ/duplicate/missing
    reason: str   # человекочитаемая причина на русском


def _blank(value: object) -> bool:
    """Поле пусто для протокола: None, не строка или одни пробелы."""
    return not isinstance(value, str) or not value.strip()


def _valid_date(value: object) -> bool:
    """Дата evidence — YYYY-MM-DD: либо типизированный date из YAML,
    либо строка в том же формате (datetime не дата — отказ)."""
    if isinstance(value, datetime.datetime):
        return False
    if isinstance(value, datetime.date):
        return True
    if not isinstance(value, str):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def load_cards(path: pathlib.Path | None = None) -> list[dict]:
    """Карты из данных; path=None -> пакетный organs/donation.yaml."""
    p = path if path is not None else DONATION_PATH
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("cards"), list):
        raise ValueError(f"донорские карты повреждены: {p}")
    return data["cards"]


def _evidence_problems(card: dict) -> list[str]:
    """Нарушения evidence: пусто, нет даты/URL/факта, url не https."""
    evidence = card.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return ["evidence отсутствует — карта без доказательств (нужна хотя бы одна запись {date, url, fact})"]
    problems: list[str] = []
    for i, item in enumerate(evidence, start=1):
        if not isinstance(item, dict):
            problems.append(f"evidence[{i}] — не словарь")
            continue
        if not _valid_date(item.get("date")):
            problems.append(f"evidence[{i}]: дата отсутствует или не YYYY-MM-DD")
        url = item.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            problems.append(f"evidence[{i}]: url отсутствует или не https")
        if _blank(item.get("fact")):
            problems.append(f"evidence[{i}]: факт пуст")
    return problems


def verdict(
    card: dict,
    registry_repos: set[str],
    seen: set[str],
    organ: str = "",
) -> Decision:
    """Вердикт для одной карты. Семантика (порядок проверки существен):
    1) repo/protocol/decision отсутствуют или вне словарей -> 'missing';
    2) repo уже встречался -> 'duplicate';
    3) repo не в живом реестре -> 'unknown-organ';
    4) protocol 'cla' + decision 'donate' -> отказ 'collar';
    5) protocol 'unverified' + decision 'donate' -> отказ 'untyped';
    6) evidence повреждён (пуст, без даты/URL/факта) -> отказ 'missing';
    7) иначе ok, rule = decision.

    Правило 'not-mutual' (donate только тому, чья лицензия в allowed матрицы
    SPEC-0006) требует лицензии органа из живого реестра — оно применяется
    в verdict_full, который несёт реестровые записи целиком.
    """
    repo = card.get("repo") if isinstance(card, dict) else None
    protocol = card.get("protocol") if isinstance(card, dict) else None
    decision = card.get("decision") if isinstance(card, dict) else None
    organ_name = organ or (repo if isinstance(repo, str) else "")

    absent: list[str] = []
    if _blank(repo):
        absent.append("repo")
    if _blank(protocol):
        absent.append("protocol (из " + ", ".join(PROTOCOLS) + ")")
    elif protocol not in PROTOCOLS:
        absent.append(f"protocol '{protocol}' вне словаря")
    if _blank(decision):
        absent.append("decision (из " + ", ".join(DECISIONS) + ")")
    elif decision not in DECISIONS:
        absent.append(f"decision '{decision}' вне словаря")
    if absent:
        return Decision(False, organ_name, str(protocol or ""), str(decision or ""), "missing", "не указано: " + ", ".join(absent))

    repo_s, protocol_s, decision_s = str(repo), str(protocol), str(decision)
    organ_name = organ_name or repo_s

    if repo_s in seen:
        return Decision(False, organ_name, protocol_s, decision_s, "duplicate", f"дубликат карты: '{repo_s}' уже проверен")

    if repo_s not in registry_repos:
        return Decision(False, organ_name, protocol_s, decision_s, "unknown-organ", f"орган '{repo_s}' отсутствует в живом реестре — кровь отдаётся только органам тела")

    if protocol_s == "cla" and decision_s == "donate":
        return Decision(False, organ_name, protocol_s, decision_s, "collar", "CLA — ошейник: права на кровь переходят хозяину репозитория; донорство запрещено, патч живёт внутри организма (SPEC-0009)")

    if protocol_s == "unverified" and decision_s == "donate":
        return Decision(False, organ_name, protocol_s, decision_s, "untyped", "орган не типирован: сначала донорское типирование, потом донорство")

    problems = _evidence_problems(card if isinstance(card, dict) else {})
    if problems:
        return Decision(False, organ_name, protocol_s, decision_s, "missing", "; ".join(problems))

    return Decision(True, organ_name, protocol_s, decision_s, decision_s, _ok_reason(protocol_s, decision_s))


def _ok_reason(protocol: str, decision: str) -> str:
    if decision == "donate":
        return f"протокол '{protocol}': ошейников не обнаружено, кровь можно отправлять в upstream (перепроверка при открытии PR)"
    if decision == "patch-inside":
        return f"протокол '{protocol}': кровь живёт внутри организма, upstream не трогается"
    return "орган потребляется внешне: донорство не имеет смысла"


def verdict_full(card: dict, registry_entries: dict[str, dict], allowed_licenses: set[str], seen: set[str]) -> Decision:
    """Полный вердикт с реестровыми записями: добавляет правило 'not-mutual'."""
    base = verdict(card, set(registry_entries), seen)
    if not base.ok or base.decision != "donate":
        return base
    entry = registry_entries.get(base.organ) or {}
    license_ = entry.get("license_pre")
    if _blank(license_):
        return Decision(False, base.organ, base.protocol, base.decision, "missing", "у органа реестра нет license_pre — сверка взаимности невозможна (fail-closed)")
    license_s = str(license_)
    if license_s not in allowed_licenses:
        return Decision(False, base.organ, base.protocol, base.decision, "not-mutual", f"дарим тому, кто дарит: лицензия органа '{license_s}' вне allowed матрицы иммунитета — донорство без адресата")
    reason = "взаимность подтверждена: лицензия '" + license_s + "' в allowed; " + base.reason
    return Decision(True, base.organ, base.protocol, base.decision, base.rule, reason)


def check_cards(cards: list[dict], registry: dict, matrix: dict) -> list[Decision]:
    """Проверка перечня карт против живого реестра и матрицы иммунитета."""
    repos = load_registry_repos_from(registry)
    entries = load_registry_entries_from(registry)
    allowed = {str(item) for item in (matrix.get("allowed") or [])}
    decisions: list[Decision] = []
    seen: set[str] = set()
    for card in cards or []:
        if not isinstance(card, dict):
            decisions.append(Decision(False, "", "", "", "missing", "карта — не словарь (fail-closed)"))
            continue
        decisions.append(verdict_full(card, entries, allowed, seen))
        seen.add(str(card.get("repo", "")) if isinstance(card, dict) else "")
    return decisions


def load_registry_repos_from(registry: dict) -> set[str]:
    """Множество repo из разобранного реестра."""
    repos = set()
    for entry in registry.get("organs") or []:
        if isinstance(entry, dict) and entry.get("repo"):
            repos.add(str(entry["repo"]))
    return repos


def load_registry_entries_from(registry: dict) -> dict[str, dict]:
    """Словарь repo -> запись реестра."""
    return {str(entry["repo"]): entry for entry in registry.get("organs") or [] if isinstance(entry, dict) and entry.get("repo")}


def run_check(
    donation_path: pathlib.Path | None = None,
    registry_path: pathlib.Path | None = None,
    matrix_path: pathlib.Path | None = None,
    out=sys.stdout,
) -> int:
    """Гейт: проверить карты донорства; вернуть 0 если все ok, иначе 1.
    Вывод: по строке на карту ('OK <organ> <protocol> <decision>' или
    'FAIL <organ> <protocol> <decision> (<rule>): <reason>'), в конце итог
    'TRANSPLANT: N ok, M failed' либо 'TRANSPLANT: FAIL (N ok, M failed)'.
    Ошибка чтения/парсинга файлов — сообщение + отказ (fail-closed).
    Дефолт out разрешается в момент вызова (под pytest capsys актуальный sys.stdout
    подменяется после импорта модуля)."""
    if out is _IMPORT_STDOUT:
        out = sys.stdout

    try:
        cards = load_cards(donation_path)
        registry = yaml.safe_load((registry_path if registry_path is not None else REGISTRY_PATH).read_text(encoding="utf-8"))
        matrix = yaml.safe_load((matrix_path if matrix_path is not None else MATRIX_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"TRANSPLANT: FAIL: данные не загружены: {exc}", file=out)
        return 1
    if not isinstance(registry, dict) or not isinstance(registry.get("organs"), list):
        print("TRANSPLANT: FAIL: реестр повреждён", file=out)
        return 1
    if not isinstance(matrix, dict) or not isinstance(matrix.get("allowed"), list):
        print("TRANSPLANT: FAIL: матрица иммунитета повреждена", file=out)
        return 1

    ok_count = 0
    failed = 0
    for decision in check_cards(cards, registry, matrix):
        if decision.ok:
            ok_count += 1
            print(f"OK {decision.organ} {decision.protocol} {decision.decision}", file=out)
        else:
            failed += 1
            print(f"FAIL {decision.organ} {decision.protocol} {decision.decision} ({decision.rule}): {decision.reason}", file=out)

    if failed:
        print(f"TRANSPLANT: FAIL ({ok_count} ok, {failed} failed)", file=out)
        return 1
    print(f"TRANSPLANT: {ok_count} ok, {failed} failed", file=out)
    return 0


def main(argv=None) -> int:
    """CLI: python -m immune.donation [--donation PATH] [--registry PATH] [--matrix PATH]."""
    parser = argparse.ArgumentParser(
        prog="python -m immune.donation",
        description="Донорский протокол COMMONS (SPEC-0009): карты донорства органов — дарим только по рукопожатию и тому, кто дарит.",
    )
    parser.add_argument("--donation", type=pathlib.Path, default=None, help="путь к картам донорства (по умолчанию organs/donation.yaml)")
    parser.add_argument("--registry", type=pathlib.Path, default=None, help="путь к реестру органов (по умолчанию organs/registry.yaml)")
    parser.add_argument("--matrix", type=pathlib.Path, default=None, help="путь к матрице иммунитета (по умолчанию пакетная license-matrix.yaml)")
    args = parser.parse_args(argv)
    return run_check(args.donation, args.registry, args.matrix)


if __name__ == "__main__":
    sys.exit(main())
