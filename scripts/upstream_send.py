#!/usr/bin/env python3
"""Отправка патча в upstream-орган: гейт карт → проверка очереди → POST PR.

SPEC-0009 v0.1.2 п.9 «Очередь — в момент отправки»: очередь дефекта проверяется
живым поиском в момент отправки, а не в момент разведки — очереди формируются
за часы, вердикт разведки устаревает к моменту POST. Порядок fail-closed:

  1) карта донорства — чистый вердикт immune.donation (без сети): орган без
     карты, ошейник, непотипированность, невзаимность — POST не выполняется;
  2) очередь — живой поиск `repo:ORG/REPO is:pr is:open <жанр>`: открытые PR
     того же жанра → отказ queue-occupied, патч остаётся резервом в форке;
  3) POST — только по флагу --send и только после двух зелёных гейтов.

Итог словами (G3): `UPSTREAM: queue-clear` / `UPSTREAM: queue-occupied (#N …)`
/ `UPSTREAM: FAIL (<rule>): <reason>`; при отправке — `UPSTREAM: PR <url>`.

Токен: env GH_CLASSIC_TOKEN или GITHUB_TOKEN; без токена поиск идёт
неаутентифицированно (10 запросов/мин) — для POST нужен токен с правом PR.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from immune import donation  # noqa: E402  (импорт после sys.path — запуск из любого cwd)

API = "https://api.github.com"
_SEARCH_IMPORTED_STDOUT = object()


class SearchError(RuntimeError):
    """Сеть/лимиты поиска — отказ, не тишина (G1)."""


def github_search_issues(query: str) -> list[dict]:
    """Живой поиск GitHub: список {number, title} открытых PR по запросу."""
    token = os.environ.get("GH_CLASSIC_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "commons-upstream-send",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = API + "/search/issues?" + urllib.parse.urlencode({"q": query, "per_page": "10"})
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SearchError(f"HTTP {exc.code}: {body[:200]}") from exc
    except urllib.error.URLError as exc:
        raise SearchError(f"сеть недоступна: {exc.reason}") from exc
    return [
        {"number": int(item["number"]), "title": str(item.get("title", ""))}
        for item in data.get("items", [])
        if isinstance(item, dict) and "number" in item
    ]


def queue_verdict(repo: str, keywords: str, search_fn=github_search_issues) -> tuple[bool, str, str]:
    """Вердикт очереди (п.9): (ok, rule, reason). Fail-closed на пустом жанре."""
    genre = (keywords or "").strip()
    if not genre:
        return False, "missing-keywords", "жанр дефекта не указан — поиск вслепую не выполняется (G1)"
    query = f"repo:{repo} is:pr is:open {genre}"
    try:
        items = search_fn(query)
    except SearchError as exc:
        return False, "search-failed", f"поиск не выполнен: {exc}"
    if items:
        listed = ", ".join(f"#{item['number']} «{item['title'][:60]}»" for item in items[:5])
        extra = "" if len(items) <= 5 else f" … (+{len(items) - 5})"
        return False, "queue-occupied", f"очередь занята: {listed}{extra} — PR не создаётся, патч остаётся резервом в форке"
    return True, "queue-clear", f"открытых PR по жанру «{genre}» нет"


def map_verdict(repo: str) -> tuple[bool, str, str]:
    """Гейт карт донорства (п.4–6): чистая функция над живыми данными, без сети."""
    try:
        cards = donation.load_cards()
        registry = donation.REGISTRY_PATH.read_text(encoding="utf-8") if hasattr(donation, "REGISTRY_PATH") else (REPO_ROOT / "organs/registry.yaml").read_text(encoding="utf-8")
        matrix_path = getattr(donation, "MATRIX_PATH", None)
        matrix_text = matrix_path.read_text(encoding="utf-8") if matrix_path else (REPO_ROOT / "immune/license-matrix.yaml").read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        return False, "missing", f"данные донорства не загружены: {exc}"

    import yaml  # локальный импорт: только для этого гейта

    try:
        registry_dict = yaml.safe_load(registry)
        matrix_dict = yaml.safe_load(matrix_text)
    except yaml.YAMLError as exc:
        return False, "missing", f"YAML донорства повреждён: {exc}"

    entry = None
    card = None
    for item in cards:
        if isinstance(item, dict) and str(item.get("repo", "")) == repo:
            card = item
            break
    if card is None:
        return False, "no-card", f"орган '{repo}' без карты донорства — донорства нет (G1): сначала типирование, потом отправка"

    entries = donation.load_registry_entries_from(registry_dict if isinstance(registry_dict, dict) else {})
    allowed = {str(item) for item in (matrix_dict.get("allowed") or [])} if isinstance(matrix_dict, dict) else set()
    decision = donation.verdict_full(card, entries, allowed, seen=set())
    return bool(decision.ok), str(decision.rule), str(decision.reason)


def github_create_pr(base_repo: str, payload: dict) -> dict:
    """POST /repos/{base_repo}/pulls. Токен обязателен."""
    token = os.environ.get("GH_CLASSIC_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not token:
        raise SearchError("нет токена (GH_CLASSIC_TOKEN/GITHUB_TOKEN) — POST невозможен")
    req = urllib.request.Request(
        f"{API}/repos/{base_repo}/pulls",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "commons-upstream-send",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SearchError(f"HTTP {exc.code}: {body[:300]}") from exc


def run_send(
    repo: str,
    keywords: str,
    head: str = "",
    base: str = "main",
    title: str = "",
    body_file: pathlib.Path | None = None,
    send: bool = False,
    search_fn=github_search_issues,
    create_fn=github_create_pr,
    out=None,
) -> int:
    """Порядок fail-closed: карта → очередь → POST. Возвращает 0/1."""
    if out is None:
        out = sys.stdout  # разрешается в момент вызова — pytest capsys видит вывод
    ok, rule, reason = map_verdict(repo)
    if not ok:
        print(f"UPSTREAM: FAIL ({rule}): {reason}", file=out)
        return 1
    print(f"OK карта: {reason}", file=out)

    ok, rule, reason = queue_verdict(repo, keywords, search_fn)
    if not ok:
        print(f"UPSTREAM: FAIL ({rule}): {reason}", file=out)
        return 1
    print(f"OK очередь: {reason}", file=out)

    if not send:
        print("UPSTREAM: queue-clear — готов к POST (добавьте --send)", file=out)
        return 0

    missing = [name for name, value in (("--head", head), ("--title", title)) if not value.strip()]
    if missing:
        print(f"UPSTREAM: FAIL (missing): не указано: {', '.join(missing)} — POST не выполняется", file=out)
        return 1
    body = body_file.read_text(encoding="utf-8") if body_file else ""
    try:
        created = create_fn(repo, {"title": title, "head": head, "base": base, "body": body})
    except SearchError as exc:
        print(f"UPSTREAM: FAIL (post-failed): {exc}", file=out)
        return 1
    print(f"UPSTREAM: PR {created.get('html_url', '(нет url в ответе)')}", file=out)
    return 0


def main(argv=None) -> int:
    """CLI: python3 scripts/upstream_send.py --repo ORG/NAME --keywords «жанр» [--send …]."""
    parser = argparse.ArgumentParser(
        prog="upstream_send.py",
        description="SPEC-0009 п.9: карта донорства → очередь в момент отправки → POST PR.",
    )
    parser.add_argument("--repo", required=True, help="upstream-репозиторий ORG/NAME")
    parser.add_argument("--keywords", required=True, help="жанр дефекта для поиска очереди (2–4 слова)")
    parser.add_argument("--head", default="", help="ветка форка OWNER:branch")
    parser.add_argument("--base", default="main", help="базовая ветка upstream (по умолчанию main)")
    parser.add_argument("--title", default="", help="заголовок PR")
    parser.add_argument("--body-file", type=pathlib.Path, default=None, help="файл с телом PR (маркдаун)")
    parser.add_argument("--send", action="store_true", help="выполнить POST (без флага — только вердикты)")
    args = parser.parse_args(argv)
    return run_send(args.repo, args.keywords, args.head, args.base, args.title, args.body_file, args.send)


if __name__ == "__main__":
    sys.exit(main())
