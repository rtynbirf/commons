#!/usr/bin/env python3
"""Doctor: гигиена дома — docs-drift ловится на автомате (0.16.0).

Блохи, пойманные живьём 2026-11-02 (внешняя рецензия коллеги-LLM + свой свип):
README протухал (294 и 253 приёмки при живых 302), ROADMAP M3 отставал от
жизни (#2808/#2810 уже открыты — «PR не создаётся»), CITATION.cff нёс счётчик
«302 приёмочных теста» в цитируемых метаданных, а обещанный в ROADMAP гейт
свежести автопортретов так и не стоял в CI. Правило дома: блоха — красный
PR, а не стыд в комментариях.

Урок при постройке: «оторванная ссылка» в llms.txt оказалась фантомом
рендера (пару символов `[m` съел дамп — урок волны-1 сработал второй раз);
машина прочитала файл — скобки на месте. Дефект верифицируется чтением
файла, не рендером: каждый гейт ниже читает файл, а не дамп.

Синтез мировых практик: link-check в CI (lychee/linkchecker), version-sync
релизных линтеров (release-please), changelog-дисциплина Keep a Changelog,
docs-tests (документация проверяется как код). Всё офлайн и детерминированно,
fail-closed: неизвестное — красное (закон иммунитета, SPEC-0006).

Запуск: python3 scripts/doctor.py   →   DOCTOR: N ok, M failed; exit 1 при M>0

Свип по расписанию (0.18.0): fleas.yml — тот же доктор + внешние ссылки
(lychee) еженедельно: ссылки умирают сами, без пушей. Новые гейты 0.18.0:
конфликт-маркеры (незалитый конфликт в md/py — блоха) и расширенные
числа-протухатели — счётчик «N практик» (урок llms.txt: «17 практик» при
живых 18) и версия в stage-бейдже (урок README: бейдж на 0.15.0 при живых
0.17). Статика не счётчик: живое число берётся из источника.

Волна-6 (0.19.0) — гейты без слепых зон, ревизия самой блохоловки: в
ROADMAP жили три живых счётчика приёмок («29 приёмок, всего 215» в 0.8.0,
«19 приёмок, всего 272» в 0.12.0, «11 приёмок» в SPEC-0009 п.9 — при живых
350), потому что ROADMAP не стоял в зоне гейта counts; README.en.md молча
отстал на три релиза (0.16.0–0.18.0), потому что version_sync смотрел
только ru. Оба дефекта того же класса, что лечили, — но в слепой зоне.
Граница жанров зафиксирована приёмкой: CHANGELOG вне зоны counts — это
журнал, исторические числа там — суть жанра (Keep a Changelog).

Волна-7 (0.20.0) — реестр хотёлок, директива Человека «МЫ ДЕЛАЕМ НЕ ДЛЯ
ЛЮДЕЙ!! МЫ ДЕЛАЕМ ДЛЯ ЧЕЛОВЕКА; САМ ИЗОБРАЖАЙ ЛЮДЕЙ С ИХ ХОТЕЛКАМИ»:
docs/personas.md — машина сама изображает людей, которым служит дом
(JTBD × персоны × continuous discovery), каждая хотёлка W-NNNN несёт
хозяина, статус и связи. Гейт wants: хотёлка-сирота (упомянута вне
реестра) и хотёлка без «Статус:» — блоха, fail-closed.

Волна-9 (0.23.0) — «иммунитет на автомате II»: синтез мировой практики
2025–2026 — secret-scanning (gitleaks, trufflehog, push protection) и
машиночитаемые отчёты линтеров (lychee-action: json + артефакт + job
summary). Гейт secrets: ключ не живёт в доме (W-0004) — ловим форму,
не содержимое, офлайн и детерминированно (SPEC-0006); скан шире прочих
гейтов — и кровь runs/: яд не история. Кровь не переписывается, но
секрет — не кровь, а яд: ротация и изъятие — единственное законное
исключение. Ловец не размножает пойманное: в отчёте маска, не секрет.
--json: память воротов машиночитаема — коллега-агент (W-0017)
перечитывает ворота без человека; человекочитаемая таблица —
scripts/doctor_report.py, оба воркфлоу печатают её в $GITHUB_STEP_SUMMARY.

Запуск: python3 scripts/doctor.py [--json] [корень]
  →  DOCTOR: N ok, M failed; exit 1 при M>0

Волна №26 (0.45.0) — Ф-0' «гигиена дисциплины» (docs/TZ.md ТЗ-0.1…ТЗ-0.5):
два новых гейта. Гейт axioms (W-0034): реестр аксиом docs/axioms.yaml (A01–A25
пакета «Human Membrane») сверяется с живыми текстами дома — свидетель-файл
жив, маркер служения в тексте на месте, красные строки несут пункт ТЗ,
упоминание A-NN вне реестра — сирота; дрейф книг от машины — блоха.
Гейт spec-first (W-0030): HEAD-коммит, меняющий blood/, synapse/, brainstem/
без правки specs/, красен — «спека раньше кода» перестаёт быть лозунгом;
git недоступен — fail-closed (непроверяемое ≠ чистое). CI обязан давать
гейту родителя коммита: checkout с fetch-depth: 2 в ci.yml (hygiene, core)
и fleas.yml — shallow-клон оставлял гейт красным на живом CI (урок 6ac04a8).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# Документы, за свежестью которых доктор следит (runs/ — пролитая кровь,
# не переписывается задним числом, поэтому вне зоны гейтов на ссылки).
README_FILES = ("README.md", "README.en.md")
LINK_FILES = ("README.md", "README.en.md", "ROADMAP.md", "CHANGELOG.md", "llms.txt")
PATH_SCOPE_FILES = ("README.md", "ROADMAP.md")
CITATION = "CITATION.cff"

COUNT_RE = re.compile(r"\b\d{2,4}\s+приём", re.IGNORECASE)
PRACTICES_RE = re.compile(r"\b\d+\s+практик", re.IGNORECASE)
BADGE_RE = re.compile(r"stage-\d+\.\d+", re.IGNORECASE)
CONFLICT_EQ_RE = re.compile(r"^={7}$", re.M)
CONFLICT_ANY_RE = re.compile(r"^(<{7}|>{7})", re.M)
MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
MD_LINK_RIGHT = re.compile(r"\]\([^)\s]+\)")
BACKTICK_PATH = re.compile(
    r"`((?:runs|specs|docs|tests|scripts|organs|pipeline|synapse|memory"
    r"|brainstem|blood|immune|openclaw|spikes)/[A-Za-z0-9_\-./]+)`"
)
SPEC_REF = re.compile(r"\bSPEC-(\d{4})\b")
ADR_REF = re.compile(r"\bADR-(\d{4})\b")
WANT_REF = re.compile(r"\bW-(\d{4})\b")
WANT_DEF_RE = re.compile(r"^#{2,3} W-(\d{4})\b", re.M)
WANT_STATUS_RE = re.compile(r"^\s*(?:[-*]\s*)?\**Статус\**\s*:", re.IGNORECASE | re.M)
PERSONAS = "docs/personas.md"
AXIOMS = "docs/axioms.yaml"
AXIOM_REF = re.compile(r"\bA(\d{2})\b")
AXIOM_STATUSES = ("СЛУЖЕНО", "PASS", "ЧАСТИЧНО", "НЕ СЛУЖЕНО", "СНЯТО")
# Порог DoD этапа (docs/TZ.md §4, такт аудита 0.48.2): число A-матрицы живёт
# только в реестре — счёт в статике книг протухает (такт аудита поймал живьём:
# книги докладывали 23/1, реестр жил 21/3 — статусы A19/A20 отстали от кода).
AXIOM_DOD_MIN_SERVED = 20
AXIOM_DOD_MAX_RED = 2
AXIOM_COUNT_BOOKS = ("docs/TZ.md", "ROADMAP.md")
# Две живые формы протухателя, обе пойманы тактом аудита: «(сейчас 23 …)» в TZ
# и «СЛУЖЕНО/PASS 23 + СНЯТО 1 …» в ROADMAP. Порог формулируется со знаком
# (≥ / ≤) — счёт без знака в книге не живёт.
AXIOM_COUNT_DUP = re.compile(r"СЛУЖЕНО/PASS[^\n]*сейчас\s+\d+")
AXIOM_COUNT_TOTAL = re.compile(r"СЛУЖЕНО/PASS\s+\d")
# Директории публичного поведения: правка без генома красит (W-0030)
CODE_SPEC_DIRS = ("blood/", "synapse/", "brainstem/")

# --- гейты: каждый возвращает (сколько файлов/пунктов чисто, список блох) ---


def _rel_lines(rel: Path) -> list[str]:
    return rel.read_text(encoding="utf-8").splitlines()


def check_no_stale_counts(root: Path) -> tuple[int, list[str]]:
    """Числа-протухатели не живут в статике: счётчик приёмок — в pytest,
    счётчик практик — в чеклисте, стадия — в бейдже без версии.
    llms.txt — в зоне: урок «17 практик» пойман живьём 2026-11-02.
    ROADMAP — в зоне с волны-6: он претендует на текущий статус, поэтому
    «N приёмок, всего M» болеет там так же, как в README (поймано живьём:
    29/215, 19/272, 11 — при живых 350). CHANGELOG сознательно вне зоны:
    это журнал, исторические числа — суть жанра; граница — приёмкой
    (test_changelog_historical_numbers_are_not_fleas)."""
    fleas: list[str] = []
    ok = 0
    rules = (
        (COUNT_RE, "протухающее число приёмок {claim!r} — счётчик живёт в `python -m pytest -q`, не в статике"),
        (PRACTICES_RE, "протухающий счётчик практик {claim!r} — живое число в docs/practices-checklist.md"),
        (BADGE_RE, "версия в stage-бейдже протухает ({claim}) — стадия в бейдже, версия в CHANGELOG"),
    )
    for name in (*README_FILES, "ROADMAP.md", CITATION, "llms.txt"):
        rel = root / name
        if not rel.exists():
            continue
        found = False
        for i, line in enumerate(_rel_lines(rel), 1):
            for regex, message in rules:
                m = regex.search(line)
                if m:
                    found = True
                    fleas.append(f"{name}:{i}: " + message.format(claim=m.group(0)))
        if not found:
            ok += 1
    return ok, fleas


def check_version_sync(root: Path) -> tuple[int, list[str]]:
    """Версия одна: pyproject == CITATION.cff == голова CHANGELOG == оба README.
    README.en.md в зоне с волны-6: en-история версий молча отстала на три
    релиза (0.16.0–0.18.0), а гейт смотрел только ru — ru/en расползлись.
    Файл отсутствует — блоха (fail-closed: в доме оба языка обязаны жить)."""
    fleas: list[str] = []
    py = (root / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version = "([^"]+)"', py, re.M)
    if not m:
        return 0, ["pyproject.toml: не найдена строка version = \"…\""]
    version = m.group(1)

    ok = 1  # pyproject — источник правды, посчитан чистым

    cite = (root / CITATION).read_text(encoding="utf-8")
    m = re.search(r"^version:\s*(\S+)", cite, re.M)
    cite_version = m.group(1) if m else None
    if cite_version != version:
        fleas.append(f"{CITATION}: version {cite_version} != pyproject {version}")
    else:
        ok += 1

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(r"^## \[(v?[\d.]+)\]", changelog, re.M)
    head = m.group(1).lstrip("v") if m else None
    if head != version:
        fleas.append(f"CHANGELOG.md: головная секция [{head}] != pyproject {version}")
    else:
        ok += 1

    for name in README_FILES:
        path = root / name
        if not path.exists():
            fleas.append(f"{name}: файл отсутствует — версии нечем жить в этом языке")
            continue
        if version not in path.read_text(encoding="utf-8"):
            fleas.append(f"{name}: текущая версия {version} не упомянута (история отстала)")
        else:
            ok += 1

    return ok, fleas


def _link_scope(root: Path) -> list[Path]:
    files = [root / name for name in LINK_FILES]
    files += sorted((root / "docs").glob("*.md"))
    files += sorted((root / "specs").glob("*.md"))
    return [p for p in files if p.exists()]


def _skip_target(target: str) -> bool:
    return (
        target.startswith(("http://", "https://", "mailto:", "#"))
        or target.endswith((".png", ".svg"))
    )


def check_relative_links(root: Path) -> tuple[int, list[str]]:
    """Каждая относительная markdown-ссылка ведёт на существующий файл (link-check)."""
    fleas: list[str] = []
    ok = 0
    for path in _link_scope(root):
        bad = False
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for m in MD_LINK.finditer(line):
                target = m.group(2).split("#", 1)[0]
                if not target or _skip_target(m.group(2)):
                    continue
                if not (path.parent / target).exists():
                    bad = True
                    fleas.append(f"{path.relative_to(root)}:{i}: битая ссылка -> {m.group(2)}")
        if not bad:
            ok += 1
    return ok, fleas


def check_orphan_links(root: Path) -> tuple[int, list[str]]:
    """Каждому `](target)` отвечает `[текст]` — оторванные скобки ловим отдельно;
    картинки-бейджи `[![alt](img)](target)` скобками не считаются — сначала
    снимаем `![…]`-узлы. Фантомный урок: дамп рендера может съесть пару
    символов `[m` — гейт читает файл, не дамп."""
    fleas: list[str] = []
    ok = 0
    for path in _link_scope(root):
        bad = False
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = re.sub(r"!\[[^\]]*\]\([^)\s]+\)", "", line)
            if len(MD_LINK_RIGHT.findall(stripped)) > len(MD_LINK.findall(stripped)):
                bad = True
                fleas.append(f"{path.relative_to(root)}:{i}: оторванная ссылка без `[текста]` -> {line.strip()[:80]!r}")
        if not bad:
            ok += 1
    return ok, fleas


def check_backtick_paths(root: Path) -> tuple[int, list[str]]:
    """Путь в кавычках-бэктиках из README/ROADMAP существует в доме.
    Имена веток (`ветка docs/…`) — не пути, пропускаются."""
    fleas: list[str] = []
    ok = 0
    for name in PATH_SCOPE_FILES:
        path = root / name
        bad = False
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for m in BACKTICK_PATH.finditer(line):
                if line[: m.start()].rstrip().endswith(("ветка", "branch")):
                    continue
                candidate = m.group(1).rstrip("./")
                if not (root / candidate).exists():
                    bad = True
                    fleas.append(f"{name}:{i}: путь не существует -> {candidate}")
        if not bad:
            ok += 1
    return ok, fleas


def _markdown_files(root: Path):
    for path in sorted(root.rglob("*.md")):
        if ".git" in path.parts or "runs" in path.parts:
            continue
        yield path


def check_spec_adr_refs(root: Path) -> tuple[int, list[str]]:
    """Каждый упомянутый SPEC-NNNN/ADR-NNNN имеет файл генома/журнала
    (файлы носят суффикс-имя: SPEC-0003-blood-envelope.md)."""
    fleas: list[str] = []
    ok = 0
    specs = root / "specs"
    adrs = root / "docs" / "adr"
    for path in _markdown_files(root):
        text = path.read_text(encoding="utf-8")
        bad = False
        for num in SPEC_REF.findall(text):
            if not any(specs.glob(f"SPEC-{num}*.md")):
                bad = True
                fleas.append(f"{path.relative_to(root)}: SPEC-{num} не имеет файла в specs/")
        for num in ADR_REF.findall(text):
            if not any(adrs.glob(f"ADR-{num}*.md")):
                bad = True
                fleas.append(f"{path.relative_to(root)}: ADR-{num} не имеет файла в docs/adr/")
        if not bad:
            ok += 1
    return ok, fleas


def check_want_refs(root: Path) -> tuple[int, list[str]]:
    """Каждая хотёлка имеет хозяина и статус (реестр docs/personas.md):
    любая W-NNNN в md дома обязана быть определена в реестре, каждая
    определённая хотёлка обязана нести «Статус:» — сирота и хотёлка без
    вердикта = блоха (fail-closed). Директива Человека 2026-11-02: машина
    сама изображает людей с их хотёлками (JTBD × персоны × continuous
    discovery) и держит их связанными с артефактами дома."""
    fleas: list[str] = []
    persona = root / PERSONAS
    defined: set[str] = set()
    if persona.exists():
        text = persona.read_text(encoding="utf-8")
        defined = set(WANT_REF.findall(text))
        if not defined:
            fleas.append(f"{PERSONAS}: реестр пуст — ни одной хотёлки W-NNNN")
        for m in WANT_DEF_RE.finditer(text):
            wid = m.group(1)
            nxt = WANT_DEF_RE.search(text, m.end())
            block = text[m.start() : nxt.start() if nxt else len(text)]
            if not WANT_STATUS_RE.search(block):
                fleas.append(f"{PERSONAS}: W-{wid} без «Статус:» — хотёлка без вердикта = обман")
    else:
        fleas.append(f"{PERSONAS}: реестра нет — хотёлкам негде жить")

    ok = 0
    for path in _markdown_files(root):
        rel = path.relative_to(root).as_posix()
        if rel == PERSONAS:
            continue
        text = path.read_text(encoding="utf-8")
        orphans = [f"W-{wid}" for wid in sorted(set(WANT_REF.findall(text))) if wid not in defined]
        if orphans:
            fleas.append(f"{rel}: хотёлки-сироты без хозяина в {PERSONAS}: {', '.join(orphans)}")
        else:
            ok += 1
    if not any(f.startswith(PERSONAS) for f in fleas):
        ok += 1  # сам реестр проверен чисто
    return ok, fleas


def check_cli_sync(root: Path) -> tuple[int, list[str]]:
    """Точки входа pyproject существуют как файлы и упомянуты в README."""
    fleas: list[str] = []
    py = (root / "pyproject.toml").read_text(encoding="utf-8")
    section = re.search(r"\[project\.scripts\]\n(.*?)(?:\n\[|\Z)", py, re.S)
    if not section:
        return 0, ["pyproject.toml: нет секции [project.scripts]"]
    readme = (root / "README.md").read_text(encoding="utf-8")
    ok = 0
    for line in section.group(1).strip().splitlines():
        m = re.match(r'^(\S+)\s*=\s*"([\w.]+):(\w+)"$', line.strip())
        if not m:
            continue
        name, module, _fn = m.groups()
        mod_path = root.joinpath(*module.split(".")).with_suffix(".py")
        if not mod_path.exists():
            fleas.append(f"pyproject.toml: {name} -> {module} не существует ({mod_path.relative_to(root)})")
        elif name not in readme:
            fleas.append(f"pyproject.toml: точка входа `{name}` не упомянута в README.md")
        else:
            ok += 1
    return ok, fleas


def check_changelog_discipline(root: Path) -> tuple[int, list[str]]:
    """Keep a Changelog: без секции [Unreleased], головная секция датирована.
    Болезнь — секция-заголовок `## [Unreleased]`, а не упоминание слова."""
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    fleas: list[str] = []
    if re.search(r"^## \[Unreleased\]", text, re.M):
        fleas.append("CHANGELOG.md: есть секция [Unreleased] — в доме версии дописываются в релиз, а не копятся")
    m = re.search(r"^## \[[\d.]+\]\s*$", text, re.M)
    if m:
        fleas.append(f"CHANGELOG.md: секция версии без даты: {m.group(0)!r}")
    return 2 - len(fleas), fleas


def _hygiene_files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.suffix not in (".md", ".py") or not path.is_file():
            continue
        if ".git" in path.parts or "runs" in path.parts:
            continue
        yield path


def check_conflict_markers(root: Path) -> tuple[int, list[str]]:
    """Незалитый конфликт в доме = блоха: <<<<<<< и >>>>>>> в md/py.
    Строка `=======` под заголовком (setext) — не блоха, пока рядом нет
    угловых маркеров. Кровь runs/ не переписывается — вне зоны."""
    fleas: list[str] = []
    ok = 0
    for path in _hygiene_files(root):
        text = path.read_text(encoding="utf-8")
        fleas_here: list[str] = []
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("<<<<<<<", ">>>>>>>")):
                fleas_here.append(
                    f"{path.relative_to(root)}:{i}: конфликт-маркер {stripped[:9]!r} — залей или отмени"
                )
        if CONFLICT_EQ_RE.search(text) and CONFLICT_ANY_RE.search(text):
            fleas_here.append(
                f"{path.relative_to(root)}: `=======` рядом с угловыми маркерами — незалитый конфликт"
            )
        fleas.extend(fleas_here)
        if not fleas_here:
            ok += 1
    return ok, fleas


# Секрет-паттерны (волна-9, синтез gitleaks/trufflehog): детерминированный
# минимум — ловим форму токена, не содержимое и не «похоже на секрет».
SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36}\b"), "GitHub PAT"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"), "GitHub fine-grained PAT"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "Slack token"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "Google API key"),
    (
        re.compile(
            r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY(?: BLOCK)?-----"
        ),
        "приватный ключ",
    ),
)

# Текстовые суффиксы в зоне секрет-скана; .env ловится отдельным именем —
# Path('.env').suffix пуст.
SECRET_SUFFIXES = frozenset({
    ".md", ".py", ".json", ".jsonl", ".yml", ".yaml", ".toml", ".cff",
    ".txt", ".sh", ".env", ".cfg", ".ini", ".js", ".ts", ".html", ".css",
    ".csv", ".sql",
})


def _mask(secret: str) -> str:
    """Ловец не размножает пойманное: в отчёт идёт маска, не секрет."""
    return secret[:8] + "…"


def check_no_secrets(root: Path) -> tuple[int, list[str]]:
    """Ключ не живёт в доме (W-0004): секрет-скан формы, не содержимого —
    синтез gitleaks/trufflehog без сети: доктор офлайн и детерминирован
    (SPEC-0006). Скан шире гигиены — и кровь runs/: яд не история; кровь
    не переписывается, но секрет не кровь, а яд: ротация и изъятие из
    истории — единственное законное исключение из append-only."""
    fleas: list[str] = []
    ok = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or (path.suffix not in SECRET_SUFFIXES and path.name != ".env"):
            continue
        if ".git" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # не текст — не наша еда (детерминированно)
        fleas_here: list[str] = []
        for i, line in enumerate(text.splitlines(), 1):
            for regex, kind in SECRET_PATTERNS:
                for m in regex.finditer(line):
                    fleas_here.append(
                        f"{path.relative_to(root)}:{i}: {kind} {_mask(m.group(0))}"
                        " — секрет не живёт в доме: отзови и ротируй (W-0004)"
                    )
        fleas.extend(fleas_here)
        if not fleas_here:
            ok += 1
    return ok, fleas


def check_axioms(root: Path) -> tuple[int, list[str]]:
    """Гейт дрейфа аксиом (W-0034, волна №26, ТЗ-0.2): матрица A01–A25 пакета
    «Human Membrane» живёт реестром docs/axioms.yaml и сверяется с домом:
    каждая строка — свидетель-файл в доме; вердикт СЛУЖЕНО/PASS обязан держать
    маркер служения в тексте свидетеля (исчез — книги разошлись с машиной,
    дрейф = блоха); ЧАСТИЧНО/НЕ СЛУЖЕНО обязаны нести пункт ТЗ; СНЯТО —
    живой ADR; упоминание A-NN вне реестра — сирота. Реестра нет — блоха
    (fail-closed, тишина гейта недопустима).

    Такт аудита (0.48.2): гейт держит порог DoD этапа (СЛУЖЕНО/PASS ≥ 20,
    красных ≤ 2 — данные гейта, G2) и запрещает книгам дублировать счёт
    A-матрицы в статике («сейчас N» — протухатель: число живёт в реестре).
    Слепая зона «маркер в свидетеле жив, а статус не перевёрнут» ловится
    порогом: отставший реестр с красными служеными аксиомами превышает
    лимит красных и красит PR — переворот статуса обязанная часть такта
    служения, а не воспоминание в коммит-сообщении."""
    fleas: list[str] = []
    registry = root / AXIOMS
    if not registry.exists():
        return 0, [f"{AXIOMS}: реестра аксиом нет — сверять нечем (fail-closed)"]
    try:
        data = yaml.safe_load(registry.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return 0, [f"{AXIOMS}: реестр нечитаем ({exc})"]
    rows = {row.get("id"): row for row in data.get("axioms", []) if isinstance(row, dict)}
    expected = {f"A{i:02d}" for i in range(1, 26)}
    missing = sorted(expected - set(rows))
    extra = sorted(set(rows) - expected)
    if missing:
        fleas.append(f"{AXIOMS}: строки реестра отсутствуют: {', '.join(missing)}")
    if extra:
        fleas.append(f"{AXIOMS}: строки вне A01–A25: {', '.join(extra)}")
    for aid, row in sorted(rows.items()):
        status = row.get("status")
        if status not in AXIOM_STATUSES:
            fleas.append(f"{AXIOMS}: {aid} — вердикт {status!r} вне словаря дома")
            continue
        witness = row.get("witness")
        if witness:
            wpath = root / witness
            if not wpath.exists():
                fleas.append(f"{AXIOMS}: {aid} — свидетель не живёт в доме: {witness}")
            elif status in ("СЛУЖЕНО", "PASS"):
                marker = row.get("marker", "")
                if marker and marker not in wpath.read_text(encoding="utf-8"):
                    fleas.append(
                        f"{AXIOMS}: {aid} — дрейф: маркер служения {marker!r} исчез из {witness}"
                    )
        elif status in ("СЛУЖЕНО", "PASS"):
            fleas.append(f"{AXIOMS}: {aid} — СЛУЖЕНО/PASS без свидетеля")
        if status in ("ЧАСТИЧНО", "НЕ СЛУЖЕНО") and not str(row.get("todo", "")).startswith("ТЗ-"):
            fleas.append(f"{AXIOMS}: {aid} — красная строка без пункта ТЗ")
        if status == "СНЯТО":
            adr = row.get("adr")
            if not adr or not (root / adr).exists():
                fleas.append(f"{AXIOMS}: {aid} — СНЯТО без живого ADR")
    # Порог DoD этапа — машина, не слова: живой пересчёт реестра против
    # границ docs/TZ.md §4 (такт аудита 0.48.2: отставший реестр красит).
    served = sum(1 for row in rows.values() if row.get("status") in ("СЛУЖЕНО", "PASS"))
    red = sum(1 for row in rows.values() if row.get("status") in ("ЧАСТИЧНО", "НЕ СЛУЖЕНО"))
    if served < AXIOM_DOD_MIN_SERVED:
        fleas.append(
            f"{AXIOMS}: порог DoD нарушен — СЛУЖЕНО/PASS {served} < {AXIOM_DOD_MIN_SERVED} (docs/TZ.md §4)"
        )
    if red > AXIOM_DOD_MAX_RED:
        fleas.append(
            f"{AXIOMS}: порог DoD нарушен — красных {red} > {AXIOM_DOD_MAX_RED} (docs/TZ.md §4)"
        )
    # Счёт A-матрицы не дублируется в статике книг: число-протухатель живёт
    # в реестре (поймано живьём: книги 23/1 — реестр 21/3).
    for book in AXIOM_COUNT_BOOKS:
        bpath = root / book
        if not bpath.exists():
            continue
        for i, line in enumerate(bpath.read_text(encoding="utf-8").splitlines(), 1):
            m = AXIOM_COUNT_DUP.search(line)
            m2 = AXIOM_COUNT_TOTAL.search(line)
            if m or m2:
                shown = (m.group(0) if m else m2.group(0))[:48]
                fleas.append(
                    f"{book}:{i}: книга дублирует счёт A-матрицы ({shown}…) — число живёт в {AXIOMS}, гейт держит порог"
                )
    defined = set(rows)
    for path in _markdown_files(root):
        rel = path.relative_to(root).as_posix()
        if rel == AXIOMS:
            continue
        orphans = [f"A{w}" for w in sorted(set(AXIOM_REF.findall(path.read_text(encoding="utf-8")))) if f"A{w}" not in defined]
        if orphans:
            fleas.append(f"{rel}: аксиомы-сироты вне реестра {AXIOMS}: {', '.join(orphans)}")
    # счёт прост и честен: сам реестр + файлы, в которых нет сирот
    ok = 1 if not any(f.startswith(AXIOMS) for f in fleas) else 0
    ok += sum(1 for path in _markdown_files(root) if not any(
        f"{path.relative_to(root).as_posix()}:" in flea for flea in fleas))
    return ok, fleas


def _head_changed_files(root: Path) -> list[str] | None:
    """Имена файлов HEAD-коммита (git diff HEAD~1..HEAD); None — git
    недоступен или не репозиторий: caller решает fail-closed."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "diff", "--name-only", "HEAD", "HEAD~1"],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def check_spec_first(root: Path) -> tuple[int, list[str]]:
    """Гейт «поведение без спеки» (W-0030, волна №26, ТЗ-0.3): HEAD-коммит,
    меняющий публичное поведение (blood/, synapse/, brainstem/) без правки
    генома (specs/), красен — «спека раньше кода» как машина, не лозунг.
    .git нет — гейт неприменим (дереву без истории нечего судить); .git есть,
    а git сломан или история пуста — fail-closed: непроверяемое ≠ чистое.
    Книги, приёмки и кровь (tests/, runs/, docs/, README) гейта не красят."""
    if not (root / ".git").exists():
        # дерево без истории (копия/синтетика) — гейту нечего судить: HEAD нет.
        # Это не «чисто», а «неприменимо»: реальный дом всегда git-репозиторий,
        # а .git с битым git — fail-closed ниже (непроверяемое ≠ чистое).
        return 1, []
    changed = _head_changed_files(root)
    if changed is None:
        return 0, ["spec-first: git недоступен или история пуста — коммит непроверяем (fail-closed)"]
    code_changes = [
        f for f in changed
        if f.endswith(".py") and f.startswith(CODE_SPEC_DIRS)
    ]
    if not code_changes:
        return 1, []
    if any(f.startswith("specs/") and f.endswith(".md") for f in changed):
        return 1, []
    return 0, [
        "spec-first: коммит меняет поведение ("
        + ", ".join(code_changes)
        + ") без правки генома specs/ — спека раньше кода (W-0030, ТЗ-0.3)"
    ]


GATES = (
    ("counts", check_no_stale_counts),
    ("versions", check_version_sync),
    ("links", check_relative_links),
    ("orphan-links", check_orphan_links),
    ("backtick-paths", check_backtick_paths),
    ("spec-adr-refs", check_spec_adr_refs),
    ("wants", check_want_refs),
    ("cli-sync", check_cli_sync),
    ("changelog", check_changelog_discipline),
    ("conflict-markers", check_conflict_markers),
    ("secrets", check_no_secrets),
    ("axioms", check_axioms),
    ("spec-first", check_spec_first),
)


def main(argv: list[str] | None = None) -> int:
    # Волна-6: CLI обязан передавать аргументы — раньше `doctor.py /путь`
    # молча проверял родной дом (argv дохло на границе __main__):
    # инъекция в копию дома возвращала ложное «чисто».
    args = list(argv) if argv else []
    json_mode = "--json" in args
    args = [a for a in args if a != "--json"]
    root = ROOT if not args else Path(args[0]).resolve()
    gates_report: list[dict] = []
    total_ok = 0
    total_fleas: list[str] = []
    for name, gate in GATES:
        ok, fleas = gate(root)
        total_ok += ok
        total_fleas.extend(fleas)
        gates_report.append({"gate": name, "ok": ok, "fleas": fleas})
        if not json_mode:
            print(f"doctor/{name}: {ok} ok, {len(fleas)} failed")
            for flea in fleas:
                print(f"  BLOHA: {flea}")
    if json_mode:
        # Волна-9: память воротов машиночитаема (W-0017) — коллега-агент
        # перечитывает ворота без человека; человекочитаемая таблица —
        # scripts/doctor_report.py (summary в воркфлоу).
        print(json.dumps(
            {
                "root": str(root),
                "gates": gates_report,
                "total_ok": total_ok,
                "total_fleas": len(total_fleas),
            },
            ensure_ascii=False,
            indent=2,
        ))
    else:
        print(f"DOCTOR: {total_ok} ok, {len(total_fleas)} failed")
    return 1 if total_fleas else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
