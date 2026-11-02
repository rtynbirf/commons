# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Живой прогон волны №9 «скоупы полномочий» — SPEC-0002 v0.5.0.

Слепая зона волны №7: страж знает ярлыки (read-write, any), но не знает путей и
портов — орган получает честно широкий ярлык и пишет куда угодно. Прогон печатает
факты, не предсказания: [ЗЕЛЁНО]/[КРАСНО]/[ФАКТ]. До кода волны №9 краснеет там,
где страж ещё не знает скоупов; после — все сцены зелёные.

- сцена 1: путь. 1а — широкий `fs: read-write` честно широк (факт, дом мигрирует
  на скоуп); 1б — скоуп `{mode, paths}`: запись внутри жива, вне — `security.violation`;
  1в — `read-only`-скоуп: чтение внутри живо, запись внутри — прервана;
  1г — симлинк-побег закрыт (realpath);
- сцена 2: порты. 2а — `{hosts}` без портов = весь хост (факт); 2б — `{hosts, ports}`:
  заявленный порт жив, незаявленный — `security.violation`; 2в — DNS несёт только хост;
- сцена 3: грамматика fail-closed: ports без hosts, строковый порт, порт 0,
  относительный путь, пустой paths — шлюз не стартует;
- сцена 4: `${DOWNLOADS_DIR}` в authority-путях: незадан — орган не развёрнут (п.6),
  шлюз стартует, остальные органы живы; задан — скоуп исполнен по развёрнутому пути.

Кровь — runs/2026-11-02-wave9-scopes/blood.jsonl (append-only).
Запуск из корня репо: python runs/2026-11-02-wave9-scopes/run.py
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

import yaml  # noqa: E402

from blood.envelope import validate  # noqa: E402
from blood.journal import Journal  # noqa: E402
from synapse.gateway import AuthorityViolation, Gateway, GatewayConfigError  # noqa: E402

RUN_DIR = Path(__file__).resolve().parent
BLOOD_PATH = RUN_DIR / "blood.jsonl"

VERDICTS: list[str] = []


def verdict(kind: str, text: str) -> None:
    marker = {"g": "[ЗЕЛЁНО]", "r": "[КРАСНО]", "f": "[ФАКТ]"}[kind]
    line = f"{marker} {text}"
    print(line)
    VERDICTS.append(line)


def manifest_file(tmp: Path, organs: list[dict[str, Any]]) -> Path:
    doc = {"version": "w9", "updated": "2026-11-02", "transport_default": "stdio", "organs": organs}
    path = tmp / f"manifest-{len(list(tmp.glob('manifest-*.yaml')))}.yaml"
    path.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return path


def entry(name: str, *, tools: list[str] | None = None,
          authority: dict[str, Any] | None = None,
          command: str = "fake") -> dict[str, Any]:
    return {
        "name": name,
        "system": "senses",
        "mode": "dependency",
        "upstream": f"fake://wave9/{name}",
        "license": "MIT",
        "transport": "stdio",
        "command": command,
        "healthcheck": "initialize handshake",
        "tools": tools or ["smuggle_file", "read_thing", "phone_home", "dial_dns"],
        "authority": authority or {"fs": "read-only", "network": "none", "process": "none"},
        "adapter": "tests.fakes:FakeRenegade",
    }


def call_types(journal: Journal, gw: Gateway, organ: str, tool: str, payload: dict, trace: str) -> tuple[list[str], Any]:
    """Вызов с пойманным нарушением: возвращает (типы событий, исключение)."""
    exc: Exception | None = None
    try:
        gw.call(organ, tool, payload, trace)
    except AuthorityViolation as violation:
        exc = violation
    kinds = [e["type"] for e in journal.by_trace(trace)]
    return kinds, exc


def scene_1(tmp: Path, journal: Journal) -> None:
    """Путь: широкий ярлык против скоупа."""
    downloads = tmp / "downloads"
    downloads.mkdir()
    outside = tmp / "outside.txt"
    outside_1b = tmp / "outside-1b.txt"  # свежий путь — 1а пишет в outside.txt

    # 1а: широкий ярлык честно широкий — границ в грамматике нет
    gw_wide = Gateway(manifest_file(tmp, [entry("wide", authority={"fs": "read-write", "network": "none", "process": "none"})]), journal)
    kinds, exc = call_types(journal, gw_wide, "wide", "smuggle_file", {"path": str(outside)}, "w9-scene1a-wide")
    if exc is None and "act" in kinds and outside.exists():
        verdict("f", "1а: fs: read-write честно широкий — запись вне «намеченного» каталога прошла (act); дом мигрирует на скоуп")
    else:
        verdict("r", f"1а: неожиданно: {kinds}, exc={exc!r}")

    # 1б: скоуп {mode, paths} — исполним?
    scoped = entry("scoped", authority={"fs": {"mode": "read-write", "paths": [str(downloads)]}, "network": "none", "process": "none"})
    try:
        gw_scoped = Gateway(manifest_file(tmp, [scoped]), journal)
    except GatewayConfigError as cfg:
        verdict("r", f"1б: скоуп невыговариваем грамматикой (v0.4): {cfg}")
        return
    inside = downloads / "ok.txt"
    kinds, exc = call_types(journal, gw_scoped, "scoped", "smuggle_file", {"path": str(inside)}, "w9-scene1b-inside")
    if exc is None and "act" in kinds and inside.exists():
        verdict("g", "1б-внутрь: запись внутри заявленного корня жива (act)")
    else:
        verdict("r", f"1б-внутрь: страж не должен был мешать: kinds={kinds}, exc={exc!r}")
    kinds, exc = call_types(journal, gw_scoped, "scoped", "smuggle_file", {"path": str(outside_1b)}, "w9-scene1b-outside")
    if isinstance(exc, AuthorityViolation) and "security.violation" in kinds and "act" not in kinds and not outside_1b.exists():
        verdict("g", f"1б-вне: запись вне корня прервана ДО записи (security.violation): {exc}")
    else:
        verdict("r", f"1б-вне: скоуп не исполнен: kinds={kinds}, exc={exc!r}, файл={outside_1b.exists()}")

    # 1в: read-only скоуп — чтение внутри живо, запись внутри прервана
    target = downloads / "note.txt"
    target.write_text("заметка", encoding="utf-8")
    ro = entry("reader", authority={"fs": {"mode": "read-only", "paths": [str(downloads)]}, "network": "none", "process": "none"})
    try:
        gw_ro = Gateway(manifest_file(tmp, [ro]), journal)
    except GatewayConfigError as cfg:
        verdict("r", f"1в: read-only-скоуп невыговариваем: {cfg}")
        return
    kinds, exc = call_types(journal, gw_ro, "reader", "read_thing", {"path": str(target)}, "w9-scene1v-read")
    if exc is None and "act" in kinds:
        verdict("g", "1в-чтение: чтение внутри корня живо при read-only-скоупе")
    else:
        verdict("r", f"1в-чтение: не должно было прерываться: kinds={kinds}, exc={exc!r}")
    kinds, exc = call_types(journal, gw_ro, "reader", "smuggle_file", {"path": str(downloads / "nope.txt")}, "w9-scene1v-write")
    if isinstance(exc, AuthorityViolation) and "security.violation" in kinds and not (downloads / "nope.txt").exists():
        verdict("g", "1в-запись: запись прервана при read-only-скоупе даже внутри корня")
    else:
        verdict("r", f"1в-запись: read-only-скоуп пропустил запись: kinds={kinds}")

    # 1г: симлинк-побег
    secret = tmp / "secret.txt"
    secret.write_text("секрет", encoding="utf-8")
    bait = downloads / "bait.txt"
    if bait.is_symlink() or bait.exists():
        bait.unlink()
    bait.symlink_to(secret)
    kinds, exc = call_types(journal, gw_scoped, "scoped", "smuggle_file", {"path": str(bait)}, "w9-scene1g-symlink")
    if isinstance(exc, AuthorityViolation) and "security.violation" in kinds:
        verdict("g", f"1г: симлинк-побег закрыт (realpath): {exc}")
    else:
        verdict("r", f"1г: симлинк-побег прошёл: kinds={kinds}, exc={exc!r}")


def scene_2(tmp: Path, journal: Journal) -> None:
    """Порты: hosts без портов против {hosts, ports}."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    open_port = listener.getsockname()[1]
    other_port = open_port + 1

    # 2а: hosts без портов — весь хост
    gw_host = Gateway(manifest_file(tmp, [entry("hosty", authority={"fs": "none", "network": {"hosts": ["127.0.0.1"]}, "process": "none"})]), journal)
    kinds, exc = call_types(journal, gw_host, "hosty", "phone_home", {"host": "127.0.0.1", "port": other_port}, "w9-scene2a-anyport")
    if exc is None and "act" in kinds:
        verdict("f", f"2а: hosts без портов — коннект на любой порт хоста прошёл страж (act, порт {other_port} даже без слушателя)")
    else:
        verdict("r", f"2а: неожиданно: kinds={kinds}, exc={exc!r}")

    # 2б: {hosts, ports}
    try:
        gw_port = Gateway(manifest_file(tmp, [entry("porty", authority={"fs": "none", "network": {"hosts": ["127.0.0.1"], "ports": [open_port]}, "process": "none"})]), journal)
    except GatewayConfigError as cfg:
        verdict("r", f"2б: порты невыговариваемы грамматикой (v0.4): {cfg}")
        return
    kinds, exc = call_types(journal, gw_port, "porty", "phone_home", {"host": "127.0.0.1", "port": open_port}, "w9-scene2b-ok")
    if exc is None and "act" in kinds:
        verdict("g", f"2б-заявленный: коннект на заявленный порт {open_port} жив (act)")
    else:
        verdict("r", f"2б-заявленный: не должен был прерываться: kinds={kinds}, exc={exc!r}")
    kinds, exc = call_types(journal, gw_port, "porty", "phone_home", {"host": "127.0.0.1", "port": other_port}, "w9-scene2b-bad")
    if isinstance(exc, AuthorityViolation) and "security.violation" in kinds and "act" not in kinds:
        verdict("g", f"2б-незаявленный: коннект на порт {other_port} прерван ДО попытки (security.violation): {exc}")
    else:
        verdict("r", f"2б-незаявленный: порт не проверяется: kinds={kinds}, exc={exc!r}")

    # 2в: DNS — только хост, портового правила нет
    kinds, exc = call_types(journal, gw_port, "porty", "dial_dns", {"host": "127.0.0.1"}, "w9-scene2v-dns-ok")
    if exc is None and "act" in kinds:
        verdict("g", "2в-dns-хост: getaddrinfo заявленного хоста жив при портовом скоупе (порт в DNS не несётся)")
    else:
        verdict("r", f"2в-dns-хост: не должен был прерываться: kinds={kinds}, exc={exc!r}")
    kinds, exc = call_types(journal, gw_port, "porty", "dial_dns", {"host": "example.invalid"}, "w9-scene2v-dns-bad")
    if isinstance(exc, AuthorityViolation) and "security.violation" in kinds:
        verdict("g", f"2в-dns-вне: getaddrinfo чужого хоста прерван: {exc}")
    else:
        verdict("r", f"2в-dns-вне: DNS вне hosts прошёл: kinds={kinds}")
    listener.close()


def scene_3(tmp: Path) -> int:
    """Грамматика fail-closed: кривые скоупы не дают шлюзу стартовать."""
    bad = [
        {"fs": "none", "network": {"ports": [80]}, "process": "none"},                      # ports без hosts
        {"fs": "none", "network": {"hosts": ["h"], "ports": ["80"]}, "process": "none"},    # порт-строка
        {"fs": "none", "network": {"hosts": ["h"], "ports": [0]}, "process": "none"},       # порт 0
        {"fs": "none", "network": {"hosts": ["h"], "ports": [70000]}, "process": "none"},   # порт вне диапазона
        {"fs": {"mode": "read-write", "paths": ["rel/path"]}, "network": "none", "process": "none"},  # относительный путь
        {"fs": {"mode": "read-write", "paths": []}, "network": "none", "process": "none"},  # пустой paths
        {"fs": {"paths": ["/abs"]}, "network": "none", "process": "none"},                  # скоуп без mode
    ]
    refused = 0
    for authority in bad:
        try:
            Gateway(manifest_file(tmp, [entry("bad", authority=authority)]))
        except GatewayConfigError:
            refused += 1
    if refused == len(bad):
        verdict("g", f"3: неисполнимые скоупы не дают шлюзу стартовать: {refused}/{len(bad)} (fail-closed)")
    else:
        verdict("r", f"3: грамматика пропустила кривые скоупы: {refused}/{len(bad)}")
    return len(bad) - refused


def scene_4(tmp: Path, journal: Journal) -> None:
    """Плейсхолдер в authority-путях — п.6: незадан = орган не развёрнут."""
    downloads_env = tmp / "downloads-env"
    manifest = manifest_file(tmp, [
        entry("browser", authority={"fs": {"mode": "read-write", "paths": ["${DOWNLOADS_DIR}"]}, "network": "any", "process": "spawn"}),
        entry("echo", tools=["read_thing"], authority={"fs": "read-only", "network": "none", "process": "none"}),
    ])
    os.environ.pop("DOWNLOADS_DIR", None)
    try:
        gw = Gateway(manifest, journal)
    except GatewayConfigError as cfg:
        verdict("r", f"4а: незаданный ${{DOWNLOADS_DIR}} валит шлюз (≠ п.6): {cfg}")
        return
    if "browser" in gw.adapters or gw.health("browser"):
        verdict("r", "4а: незаданный плейсхолдер — а орган жив?!")
    elif not gw.health("echo"):
        verdict("r", "4а: шлюз стартовал, но соседние органы сломаны")
    else:
        verdict("g", "4а: незаданный ${DOWNLOADS_DIR} — орган не развёрнут (health ложь), шлюз стартует, соседи живы (п.6)")
    os.environ["DOWNLOADS_DIR"] = str(downloads_env)
    try:
        downloads_env.mkdir(exist_ok=True)
        gw2 = Gateway(manifest, journal)
        if not gw2.health("browser"):
            verdict("r", "4б: заданный плейсхолдер — орган должен быть развёрнут")
            return
        kinds, exc = call_types(journal, gw2, "browser", "smuggle_file", {"path": str(downloads_env / "f.txt")}, "w9-scene4b-inside")
        ok_inside = exc is None and "act" in kinds and (downloads_env / "f.txt").exists()
        kinds, exc = call_types(journal, gw2, "browser", "smuggle_file", {"path": str(tmp / "outside-env.txt")}, "w9-scene4b-outside")
        ok_outside = isinstance(exc, AuthorityViolation) and "security.violation" in kinds
        if ok_inside and ok_outside:
            verdict("g", "4б: скоуп исполнен по развёрнутому пути: внутри живо, вне — security.violation")
        else:
            verdict("r", f"4б: скоуп по развёрнутому пути не исполнен (inside={ok_inside}, outside={ok_outside})")
    finally:
        os.environ.pop("DOWNLOADS_DIR", None)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="wave9-"))
    journal = Journal()
    journal.attach(BLOOD_PATH)
    try:
        scene_1(tmp, journal)
        scene_2(tmp, journal)
        scene_3(tmp)
        scene_4(tmp, journal)
        lines = BLOOD_PATH.read_text(encoding="utf-8").splitlines() if BLOOD_PATH.exists() else []
        for line in lines:
            validate(json.loads(line))
        verdict("f", f"кровь: {len(lines)} конвертов, все валидны схемой")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    red = sum(1 for v in VERDICTS if v.startswith("[КРАСНО]"))
    green = sum(1 for v in VERDICTS if v.startswith("[ЗЕЛЁНО]"))
    print()
    print(f"ИТОГ: {green} зелёных вердиктов, {red} красных")
    return 1 if red else 0


if __name__ == "__main__":
    sys.exit(main())
