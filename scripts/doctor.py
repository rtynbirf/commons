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
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

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

# W-0030 (0.43.0, зерно D3 коллег, находка F-09): публичное поведение дома —
# три пакета ствола и крови; specs/ — геном. Правило «спека раньше кода».
BEHAVIOR_PREFIXES = ("blood/", "synapse/", "brainstem/")
SPEC_PREFIX = "specs/"
SPEC_DRIFT_ENV = "SPEC_DRIFT_BASE"

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


def check_spec_drift(root: Path) -> tuple[int, list[str]]:
    """Поведение без спеки — красный PR (W-0030, 0.43.0, зерно D3 коллег, F-09).

    Принцип дома «спека меняется раньше кода» становится машиной: если в
    диффе против базы тронуты кровь/синапсы/ствол (blood/, synapse/,
    brainstem/), а specs/ не тронут — блоха на каждом таком пути. База —
    env SPEC_DRIFT_BASE (CI ставит base.sha PR'а; для пушей — HEAD~1;
    локально по умолчанию HEAD — незакоммиченное). Новые файлы (untracked)
    видны так же: новое поведение без спеки — та же блоха. Git недоступен —
    fail-closed: гейт красный, а не слепой (закон иммунитета, SPEC-0006).
    Граница честно названа: гейт судит дифф против базы, а не историю —
    старые расползания ловят гематология и ревизии.
    """
    base = os.environ.get(SPEC_DRIFT_ENV, "").strip() or "HEAD"
    try:
        diff = subprocess.run(
            ["git", "-C", str(root), "-c", "core.quotepath=off", "diff", "--name-only", base],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        ).stdout.splitlines()
        status = subprocess.run(
            ["git", "-C", str(root), "-c", "core.quotepath=off", "status", "--porcelain", "-uall"],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        ).stdout.splitlines()
    except (OSError, subprocess.SubprocessError) as exc:
        detail = (exc.stderr if hasattr(exc, "stderr") and exc.stderr else str(exc)).strip()[:200]
        return 0, [
            f"spec-drift: гейт не смог прочитать diff против {base!r} ({detail}) — fail-closed, красный без суждения"
        ]

    changed = {line.strip() for line in diff if line.strip()}
    for line in status:
        if line.startswith("?? "):
            changed.add(line[3:].strip())
    behavior = sorted(p for p in changed if p.startswith(BEHAVIOR_PREFIXES))
    specs_touched = any(p.startswith(SPEC_PREFIX) for p in changed)
    fleas: list[str] = []
    if behavior and not specs_touched:
        for path in behavior:
            fleas.append(
                f"spec-drift: {path}: поведение без спеки — specs/ не тронуты (спека раньше кода, W-0030)"
            )
    return (0 if fleas else 1), fleas


AXIOMS_FILE = Path("docs/axioms.yaml")
AXIOM_IDS = [f"A{i:02d}" for i in range(1, 26)]
AXIOM_VERDICTS = {"pass", "partial", "served", "adr", "open"}


def check_axioms(root: Path) -> tuple[int, list[str]]:
    """W-0034 (0.44.0, волна №25): гейт дрейфа аксиом — живая матрица A01–A25.

    Ревизия 2026-11-03 сверила матрицу пакета A01–A25 с телом и оставила её
    в пролитой крови (runs/2026-11-03-revision/) — история, не живой закон.
    Дрейф версии, ссылок и хотёлок доктор ловил, а аксиомы расползались
    молча. Теперь матрица живёт данными docs/axioms.yaml: вердикт — только
    из словаря дома; указатель доказательства обязан существовать на диске;
    открытая/частичная аксиома обязана называть план (где закрывается).
    Fail-closed: нечитаемый yaml — красный без суждения (закон иммунитета,
    SPEC-0006), а не «ну похоже на правду».
    """
    fleas: list[str] = []
    path = root / AXIOMS_FILE
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return 0, ["axioms: docs/axioms.yaml нет — матрицы нет, закона нет (fail-closed)"]
    except Exception as exc:  # noqa: BLE001 — нечитаемое судим целиком
        return 0, [f"axioms: docs/axioms.yaml не читается ({str(exc)[:120]}) — красный без суждения"]
    if not isinstance(data, dict) or not isinstance(data.get("axioms"), list):
        return 0, ["axioms: docs/axioms.yaml не содержит список axioms — формат дрейфанул"]
    axioms = data["axioms"]
    ids = [a.get("id") for a in axioms if isinstance(a, dict)]
    if ids != AXIOM_IDS:
        missing = [i for i in AXIOM_IDS if i not in ids]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        fleas.append(
            f"axioms: матрица не полна — пропало {missing or '—'}, дубликаты {dupes or '—'} "
            f"(тишина не значит «всё хорошо»)"
        )
    for a in axioms:
        if not isinstance(a, dict):
            fleas.append("axioms: чужая строка в матрице (не отображение) — блоха")
            continue
        aid = a.get("id", "?")
        verdict = a.get("verdict")
        if verdict not in AXIOM_VERDICTS:
            fleas.append(f"axioms: {aid}: чужой вердикт {verdict!r} — словарь дома не расширяется молча")
            continue
        for rel in a.get("evidence") or []:
            if not (root / rel).exists():
                fleas.append(f"axioms: {aid}: указатель {rel} ведёт в пустоту — фантазия, не доказательство")
        if verdict in {"served", "pass", "adr"} and not (a.get("evidence") or []):
            fleas.append(f"axioms: {aid}: вердикт {verdict!r} без доказательства — обман, не вердикт")
        if verdict == "partial" and not (a.get("evidence") or []):
            fleas.append(f"axioms: {aid}: «частично» без сделанного — обман, не вердикт")
        if verdict in {"open", "partial"} and not a.get("plan"):
            fleas.append(f"axioms: {aid}: открытая аксиома без плана — обман («когда-нибудь» не план)")
    ok = sum(1 for a in axioms if isinstance(a, dict) and not any(f.startswith(f"axioms: {a.get('id', '?')}:") for f in fleas))
    return ok, fleas


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
    ("spec-drift", check_spec_drift),
    ("axioms", check_axioms),
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
