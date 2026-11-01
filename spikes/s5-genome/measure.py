#!/usr/bin/env python3
"""Спайк S5: геном — фича через полный цикл spec-kit (docs/spikes.md, ROADMAP M3).

Гипотеза: спека → план → задачи → реализация работает как рабочий процесс организма.
Метод: одна реальная фича COMMONS проводится через /specify → /plan → /tasks → /implement;
метрики — итерации до сходимости, доля задач с правкой спеки, дрейф спеки от кода.

Харнесс умеет два режима. Режим --selfcheck (он же default) — офлайн-самопроверка
«спека ↔ код» в три шага: анатомия спек, покрытие гарантий упоминаниями в тестах,
маппинг разделов на spec-kit. Режим --selfcheck работает офлайн и входит в CI; без
установленного specify режим --spec-kit печатает NO_SPEC_KIT (код 2) — цифры не
выдумываются.

Запуск:
  python3 spikes/s5-genome/measure.py --selfcheck   # офлайн, стабильно в CI
  python3 spikes/s5-genome/measure.py --spec-kit    # полный цикл, нужен specify на PATH
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # spikes/s5-genome/measure.py → корень репо
SPECS_DIR = REPO_ROOT / "specs"
TESTS_DIR = REPO_ROOT / "tests"

# Соответствие разделов наших спек разделам шаблона spec-kit (рабочая пара спайка).
# Спайк сравнивает структуру сгенерированных шаблонов, но не копирует код spec-kit
# (ADR-0001, PROVENANCE.md). Живая проверка стороны шаблона — в режиме --spec-kit.
SECTION_MAPPING: list[tuple[str, str]] = [
    ("Назначение", "User Story"),
    ("Контракт", "Requirements"),
    ("Гарантии", "Acceptance/Гарантии"),
    ("Отказные режимы", "Edge Cases"),
]

INSTALL_HINT = "Установка: uvx --from git+https://github.com/github/spec-kit.git specify"

_SECTION_HEAD_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)  # разделы наших спек: «## …»
_TEMPLATE_HEAD_RE = re.compile(r"^#{2,3}\s+(.+?)\s*$", re.MULTILINE)  # шаблон: «## …» и «### …»
_TITLE_RE = re.compile(r"^#\s+(SPEC-\d+):\s*(.+?)\s*$", re.MULTILINE)
_STATUS_RE = re.compile(r"^Статус:\s*(.+?)\s*$", re.MULTILINE)
_CONTRACT_ITEM_RE = re.compile(r"^\s*\d+\.\s", re.MULTILINE)
_GUARANTEE_MARK_RE = re.compile(r"^\s*-\s*\*\*(G\d+)\b", re.MULTILINE)


# --------------------------------------------------------------------------
# Парсинг спек (уровень модуля — импортируется тестами; регулярки, без внешних парсеров)
# --------------------------------------------------------------------------


def split_sections(text: str) -> dict[str, str]:
    """Разрезает markdown по заголовкам «## Название» → {название: тело раздела}."""
    heads = list(_SECTION_HEAD_RE.finditer(text))
    sections: dict[str, str] = {}
    for i, head in enumerate(heads):
        body_end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        sections[head.group(1).strip()] = text[head.end():body_end]
    return sections


def section_body(sections: dict[str, str], name: str) -> str:
    """Тело раздела: точное имя, иначе префикс («Гарантии» ← «Гарантии (M3)»), иначе пусто."""
    if name in sections:
        return sections[name]
    for title, body in sections.items():
        if title.startswith(name):
            return body
    return ""


def extract_guarantee_ids(text: str) -> list[str]:
    """ID гарантий («G1», «G2», …) по маркерам «- **G1 Название.**» в разделе «## Гарантии»."""
    body = section_body(split_sections(text), "Гарантии")
    ids: list[str] = []
    for match in _GUARANTEE_MARK_RE.finditer(body):
        if match.group(1) not in ids:
            ids.append(match.group(1))
    return ids


def parse_spec(text: str) -> dict:
    """Анатомия одной спеки (без внешних парсеров).

    Ключи: id («SPEC-0001»), title (название из заголовка), status (строка «Статус: …»
    целиком), contract_count (число строк «N.» в «## Контракт»), guarantees (список id
    вида «G1» из «## Гарантии»), sections (имена найденных разделов).
    """
    sections = split_sections(text)
    title = _TITLE_RE.search(text)
    status = _STATUS_RE.search(text)
    contract = section_body(sections, "Контракт")
    return {
        "id": title.group(1) if title else "",
        "title": title.group(2).strip() if title else "",
        "status": status.group(1).strip() if status else "",
        "contract_count": len(_CONTRACT_ITEM_RE.findall(contract)),
        "guarantees": extract_guarantee_ids(text),
        "sections": list(sections),
    }


def load_specs() -> dict[str, dict]:
    """Анатомия всех specs/SPEC-*.md → {id спеки: parse_spec(...), …}."""
    specs: dict[str, dict] = {}
    for path in sorted(SPECS_DIR.glob("SPEC-*.md")):
        parsed = parse_spec(path.read_text(encoding="utf-8"))
        specs[parsed["id"] or path.stem] = parsed
    return specs


def has_section(spec: dict, name: str) -> bool:
    """Есть ли в спеке раздел с таким именем (или начинающийся с него)."""
    return any(title == name or title.startswith(name) for title in spec["sections"])


def load_tests_text() -> dict[str, str]:
    """Тексты tests/*.py: чистое чтение, упоминания ищутся подстрокой (эвристика)."""
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(TESTS_DIR.glob("*.py"))}


def mention_files(guarantee_id: str, tests: dict[str, str]) -> list[str]:
    """Файлы tests/*.py, где встречается подстрока «G1», «G2», …"""
    return sorted(name for name, body in tests.items() if guarantee_id in body)


def short_status(status: str) -> str:
    """Первый сегмент строки «Статус: …» до « · » — для компактной таблицы."""
    return status.split(" · ")[0].strip()


def section_matches(target: str, heading: str) -> bool:
    """Эвристика: заголовок шаблона покрывает цель, если содержит слово цели (≥3 букв).

    «Acceptance/Гарантии» — любая из сторон через «/»: достаточно английской или русской.
    """
    low = heading.lower()
    for alternative in target.split("/"):
        for word in re.findall(r"[а-яёa-z]{3,}", alternative.lower()):
            if word in low:
                return True
    return False


def template_section_titles(text: str) -> list[str]:
    """Заголовки шаблона spec-kit («## …» и «### …»): сравнение по структуре, не по коду."""
    return [match.group(1).strip() for match in _TEMPLATE_HEAD_RE.finditer(text)]


def mapping_status(specs: dict[str, dict], ours: str, template_titles: list[str] | None, theirs: str) -> str:
    """Маппинг пары разделов: «полный», когда есть обе стороны пары.

    Офлайн (template_titles is None) проверена только наша сторона — раздел во всех
    спеках; сторона шаблона spec-kit подтверждается живым specify в режиме --spec-kit.
    """
    our_ok = all(has_section(spec, ours) for spec in specs.values())
    if template_titles is None:
        return "полный" if our_ok else "частичный"
    template_ok = any(section_matches(theirs, title) for title in template_titles)
    if our_ok and template_ok:
        return "полный"
    return "частичный" if our_ok or template_ok else "нет"


# --------------------------------------------------------------------------
# Режим --selfcheck: офлайн-самопроверка «спека ↔ код» (единственный замер спайка в CI)
# --------------------------------------------------------------------------


def run_selfcheck() -> int:
    """Три шага самопроверки; печатает markdown-таблицы, exit 0."""
    specs = load_specs()
    tests = load_tests_text()

    print("Спайк S5: самопроверка «спека ↔ код» (офлайн, только стандартная библиотека)")
    print()

    print("Шаг 1. Анатомия спек specs/SPEC-0001..0003 (пункты контракта — строки «N.» в")
    print("«## Контракт», гарантии — маркеры «- **G1» в «## Гарантии»; регулярки, без внешних парсеров)")
    print("| спека | название | статус | пунктов контракта | гарантий |")
    print("| --- | --- | --- | --- | --- |")
    for spec in specs.values():
        print(f"| {spec['id']} | {spec['title']} | {short_status(spec['status'])} "
              f"| {spec['contract_count']} | {len(spec['guarantees'])} |")
    print()

    print("Шаг 2. Покрытие гарантий упоминаниями в tests/*.py — ЭТО ЭВРИСТИКА ПО УПОМИНАНИЯМ")
    print("(подстрока «G1», «G2», … по телу файла), НЕ доказательство покрытия тестами.")
    print("| гарантия | спека | тест есть / теста нет | где упомянута |")
    print("| --- | --- | --- | --- |")
    total = 0
    untested = 0
    for spec in specs.values():
        for guarantee_id in spec["guarantees"]:
            files = mention_files(guarantee_id, tests)
            total += 1
            if files:
                mark, where = "тест есть", ", ".join(files)
            else:
                untested += 1
                mark, where = "теста нет", "—"
            print(f"| {guarantee_id} | {spec['id']} | {mark} | {where} |")
    print()
    print(f"дрейф спека↔код: {untested}/{total} гарантий без теста (эвристика)")
    print()

    print("Шаг 3. Маппинг разделов наших спек на spec-kit: «полный», когда есть обе стороны")
    print("пары; офлайн проверена наша сторона, сторона шаблона — живым specify (--spec-kit).")
    print("| наш раздел | раздел spec-kit | найден в спеках | маппинг |")
    print("| --- | --- | --- | --- |")
    for ours, theirs in SECTION_MAPPING:
        found = sum(1 for spec in specs.values() if has_section(spec, ours))
        print(f"| {ours} | {theirs} | {found}/{len(specs)} | {mapping_status(specs, ours, None, theirs)} |")
    return 0


# --------------------------------------------------------------------------
# Режим --spec-kit: полный цикл (нужен живой specify); ошибки — честный exit 2
# --------------------------------------------------------------------------


def _fail_spec_kit(stage: str, proc: subprocess.CompletedProcess | None = None) -> int:
    """Честный отказ: полный цикл не замеряется, частичных выдуманных метрик нет."""
    print(f"SPEC_KIT_FAILED: {stage} — полный цикл не замеряется, метрики не выдумываются.")
    if proc is not None:
        tail = ((proc.stderr or "") + (proc.stdout or "")).strip()
        if tail:
            print("Ответ specify (последние строки):")
            for line in tail.splitlines()[-10:]:
                print(f"  {line}")
    return 2


def _adjusted_init(specify: str, probe: Path) -> subprocess.CompletedProcess | None:
    """Основной набор флагов не принят: сверяемся с `specify init --help` и убираем
    незадокументированные флаги. Результаты не выдумываются: не помогло — None."""
    try:
        help_proc = subprocess.run(
            [specify, "init", "--help"],
            capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    help_text = (help_proc.stdout or "") + (help_proc.stderr or "")
    if not help_text.strip():
        return None
    command = [specify, "init", str(probe)]
    if "--ai" in help_text:
        command += ["--ai", "generic"]
    if "--skip-checks" in help_text:
        command.append("--skip-checks")
    try:
        return subprocess.run(
            command, capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _generated_files(probe: Path) -> list[str]:
    """Относительные пути сгенерированных файлов (без служебного .git)."""
    return sorted(
        path.relative_to(probe).as_posix()
        for path in probe.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(probe).parts
    )


def _find_spec_template(probe: Path) -> Path | None:
    """Шаблон спеки среди сгенерированных файлов: имя содержит «spec» и «template»."""
    candidates = sorted(
        path for path in probe.rglob("*.md")
        if "spec" in path.name.lower() and "template" in path.name.lower()
    )
    return candidates[0] if candidates else None


def _probe_spec_kit(specify: str, tmp: Path) -> int:
    """Живой specify: init в tmp → список файлов → секции шаблона → сравнение с геномом."""
    probe = tmp / "probe"
    try:
        proc = subprocess.run(
            [specify, "init", str(probe), "--ai", "generic", "--skip-checks"],
            capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL,
        )
        if proc.returncode != 0:
            proc = _adjusted_init(specify, probe)
        if proc is None:
            return _fail_spec_kit("specify init не принят (справка не спасла — флаги не подстроить)")
        if proc.returncode != 0:
            return _fail_spec_kit("specify init завершился с ошибкой", proc)
    except (OSError, subprocess.SubprocessError) as exc:
        return _fail_spec_kit(f"запуск specify init упал: {exc}")

    files = _generated_files(probe)
    if not files:
        return _fail_spec_kit("specify init отработал, но файлов не создал")
    print("Полный цикл S5: specify init прошёл. Сгенерированные файлы:")
    for name in files:
        print(f"- {name}")
    print()

    template = _find_spec_template(probe)
    if template is None:
        return _fail_spec_kit("шаблон спеки (имя с «spec» и «template») среди файлов не найден")
    titles = template_section_titles(template.read_text(encoding="utf-8", errors="replace"))
    print(f"Секции шаблона спеки ({template.relative_to(probe).as_posix()}):")
    for title in titles:
        print(f"- {title}")
    print()

    specs = load_specs()
    print("Сравнение секций шаблона spec-kit с нашими SPEC-0001..0003:")
    print("| наш раздел | раздел spec-kit | сторона спек | сторона шаблона | маппинг |")
    print("| --- | --- | --- | --- | --- |")
    for ours, theirs in SECTION_MAPPING:
        our_ok = all(has_section(spec, ours) for spec in specs.values())
        template_ok = any(section_matches(theirs, title) for title in titles)
        status = "полный" if our_ok and template_ok else ("частичный" if our_ok or template_ok else "нет")
        print(f"| {ours} | {theirs} | {'есть' if our_ok else 'нет'} "
              f"| {'есть' if template_ok else 'нет'} | {status} |")
    unpaired = [
        title for title in titles
        if not any(section_matches(theirs, title) for _, theirs in SECTION_MAPPING)
    ]
    if unpaired:
        print()
        print("Разделы шаблона без пары в нашем геноме: " + "; ".join(unpaired))
    return 0


def run_spec_kit() -> int:
    """Полный цикл на живом specify; без него — NO_SPEC_KIT (код 2), без выдумок."""
    specify = shutil.which("specify")
    if specify is None:
        print("NO_SPEC_KIT: specify не на PATH — полный цикл не замеряется, спайк не врёт вместо замера.")
        print(INSTALL_HINT)
        return 2
    with tempfile.TemporaryDirectory(prefix="s5-spec-kit-") as tmp:
        return _probe_spec_kit(specify, Path(tmp))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Спайк S5: геном — фича через полный цикл spec-kit (docs/spikes.md)",
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--selfcheck", action="store_true",
                       help="офлайн-самопроверка «спека ↔ код» (по умолчанию, работает в CI)")
    modes.add_argument("--spec-kit", action="store_true", dest="spec_kit",
                       help="полный цикл specify init; без specify на PATH — NO_SPEC_KIT, код 2")
    args = parser.parse_args(argv)
    return run_spec_kit() if args.spec_kit else run_selfcheck()


if __name__ == "__main__":
    raise SystemExit(main())
