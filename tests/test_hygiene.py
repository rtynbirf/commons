# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмка гигиены дома (0.16.0): доктор ловит блох на фейковых картах, дом чист.

Гейты docs-drift (scripts/doctor.py) проверяются дважды:
1) на фейковых картах — каждая блоха обязана ловиться (fail-closed);
2) на самом доме — все гейты зелёные (самохостинг).
CI-джоба `hygiene` приговорена проверками: обещание «гейт в CI» больше
не может протухнуть молча (урок: `organ_map.py --check` существовал,
но в CI так и не стоял).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "doctor.py"

_spec = importlib.util.spec_from_file_location("doctor", SCRIPT)
doctor = importlib.util.module_from_spec(_spec)
sys.modules["doctor"] = doctor
_spec.loader.exec_module(doctor)


def _touch(root: Path, name: str, text: str = "") -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --- самохостинг: дом чист своими гейтами ---


def test_house_is_clean_by_its_own_gates() -> None:
    for name, gate in doctor.GATES:
        ok, fleas = gate(REPO_ROOT)
        assert not fleas, f"гейт {name} нашёл блох в собственном доме: {fleas}"
        assert ok > 0, f"гейт {name} не проверил ни одного файла"


# --- каждая блоха ловится на фейковой карте ---


def test_stale_count_is_caught(tmp_path: Path) -> None:
    _touch(tmp_path, "README.md", "Всего 294 приёмок.\n")
    _touch(tmp_path, "README.en.md")
    _touch(tmp_path, "CITATION.cff", "abstract: 302 приёмочных теста\n")

    ok, fleas = doctor.check_no_stale_counts(tmp_path)

    assert ok == 1  # чист только README.en.md
    assert len(fleas) == 2, fleas
    assert "README.md:1" in fleas[0]
    assert "CITATION.cff:1" in fleas[1]


def test_clean_docs_pass_count_gate(tmp_path: Path) -> None:
    _touch(tmp_path, "README.md", "python -m pytest -q  # живое число — у pytest\n")
    _touch(tmp_path, "README.en.md")
    _touch(tmp_path, "CITATION.cff", "abstract: приёмки исполняются машиной\n")

    ok, fleas = doctor.check_no_stale_counts(tmp_path)

    assert (ok, fleas) == (3, [])


def test_version_drift_is_caught(tmp_path: Path) -> None:
    _touch(tmp_path, "pyproject.toml", 'version = "0.16.0"\n')
    _touch(tmp_path, "CITATION.cff", "version: 0.15.0\n")
    _touch(tmp_path, "CHANGELOG.md", "## [0.15.0] — 2026-11-02\n")
    _touch(tmp_path, "README.md", "история отстала\n")

    ok, fleas = doctor.check_version_sync(tmp_path)

    assert len(fleas) == 3, fleas
    assert any("CITATION.cff" in f for f in fleas)
    assert any("CHANGELOG.md" in f for f in fleas)
    assert any("README.md" in f for f in fleas)
    assert ok == 1  # чист только pyproject


def test_version_sync_green(tmp_path: Path) -> None:
    _touch(tmp_path, "pyproject.toml", 'version = "0.16.0"\n')
    _touch(tmp_path, "CITATION.cff", "version: 0.16.0\n")
    _touch(tmp_path, "CHANGELOG.md", "## [0.16.0] — 2026-11-02\n")
    _touch(tmp_path, "README.md", "С 0.16.0 у организма есть гигиена дома.\n")

    ok, fleas = doctor.check_version_sync(tmp_path)

    assert (ok, fleas) == (4, [])


def test_broken_relative_link_is_caught(tmp_path: Path) -> None:
    _touch(tmp_path, "README.md", "Читай [геном](specs/SPEC-9999-gostinets.md).\n")

    ok, fleas = doctor.check_relative_links(tmp_path)

    assert ok == 0
    assert len(fleas) == 1
    assert "specs/SPEC-9999-gostinets.md" in fleas[0]


def test_external_and_anchor_links_are_skipped(tmp_path: Path) -> None:
    _touch(
        tmp_path,
        "README.md",
        "[внешнее](https://example.com) и [якорь](#раздел) и [почта](mailto:a@b.c)\n",
    )

    ok, fleas = doctor.check_relative_links(tmp_path)

    assert (ok, fleas) == (1, [])


def test_orphan_link_is_caught(tmp_path: Path) -> None:
    _touch(tmp_path, "llms.txt", "- emory/](memory/): фантом, ставший блохой\n")

    ok, fleas = doctor.check_orphan_links(tmp_path)

    assert ok == 0
    assert len(fleas) == 1


def test_orphan_gate_reads_file_not_render(tmp_path: Path) -> None:
    # Урок волны-1, сработавший дважды: дамп рендера съедает пару `[m`,
    # файл при этом цел — гейт обязан читать файл, а не дамп.
    _touch(tmp_path, "llms.txt", "- [memory/](memory/): память организма\n")

    ok, fleas = doctor.check_orphan_links(tmp_path)

    assert (ok, fleas) == (1, [])


def test_badge_image_link_is_not_an_orphan(tmp_path: Path) -> None:
    _touch(tmp_path, "README.md", "[![ci](https://example.com/badge.svg)](https://example.com/ci)\n")

    ok, fleas = doctor.check_orphan_links(tmp_path)

    assert (ok, fleas) == (1, [])


def test_ghost_backtick_path_is_caught(tmp_path: Path) -> None:
    _touch(tmp_path, "README.md", "Харнесс: `scripts/ghost.py` — его нет.\n")
    _touch(tmp_path, "ROADMAP.md", "Ветка `docs/призрак` — имя ветки, не путь.\n")

    ok, fleas = doctor.check_backtick_paths(tmp_path)

    assert len(fleas) == 1
    assert "scripts/ghost.py" in fleas[0]
    assert ok == 1  # ROADMAP чист: имя ветки не путь


def test_spec_ref_without_genome_file_is_caught(tmp_path: Path) -> None:
    _touch(tmp_path, "docs/note.md", "Смотри SPEC-9999 и ADR-9999.\n")

    ok, fleas = doctor.check_spec_adr_refs(tmp_path)

    assert ok == 0
    assert len(fleas) == 2, fleas


def test_cli_entry_without_file_is_caught(tmp_path: Path) -> None:
    _touch(
        tmp_path,
        "pyproject.toml",
        '[project.scripts]\ncommons-ghost = "soul.ghost:main"\n',
    )
    _touch(tmp_path, "README.md", "руки: commons-ghost\n")

    ok, fleas = doctor.check_cli_sync(tmp_path)

    assert ok == 0
    assert len(fleas) == 1
    assert "soul.ghost" in fleas[0]


def test_cli_entry_without_readme_mention_is_caught(tmp_path: Path) -> None:
    _touch(tmp_path, "pyproject.toml", '[project.scripts]\ncommons-real = "soul.real:main"\n')
    _touch(tmp_path, "soul/real.py", "def main(): ...\n")
    _touch(tmp_path, "README.md", "здесь точки входа не названы\n")

    ok, fleas = doctor.check_cli_sync(tmp_path)

    assert ok == 0
    assert len(fleas) == 1
    assert "не упомянута в README" in fleas[0]


def test_unreleased_section_is_caught(tmp_path: Path) -> None:
    _touch(tmp_path, "CHANGELOG.md", "## [Unreleased]\n\n## [0.15.0] — 2026-11-02\n")

    ok, fleas = doctor.check_changelog_discipline(tmp_path)

    assert ok == 1
    assert len(fleas) == 1
    assert "[Unreleased]" in fleas[0]


def test_headless_changelog_section_is_caught(tmp_path: Path) -> None:
    _touch(tmp_path, "CHANGELOG.md", "## [1.2.3]\n")

    ok, fleas = doctor.check_changelog_discipline(tmp_path)

    assert ok == 1
    assert len(fleas) == 1
    assert "без даты" in fleas[0]


# --- обещание «гейт в CI» приговорено проверками ---


def test_ci_job_pins_the_gates() -> None:
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "hygiene:" in ci, "job hygiene отсутствует в CI"
    assert "scripts/doctor.py" in ci, "доктор не стоит в CI"
    assert "organ_map.py --check" in ci, "гейт свежести автопортрета не стоит в CI"
    assert "selfmap.py" in ci and "git diff --exit-code" in ci, "свежесть selfmap не приговорена"


def test_doctor_fails_closed_on_flea_house(tmp_path: Path) -> None:
    # Дом с одной блохой обязан дать exit 1: fail-closed, а не «предупреждение».
    _touch(tmp_path, "README.md", "Всего 294 приёмок. Точки входа: commons-x\n")
    _touch(tmp_path, "README.en.md")
    _touch(tmp_path, "ROADMAP.md")
    _touch(tmp_path, "CITATION.cff", "version: 0.16.0\n")
    _touch(tmp_path, "pyproject.toml", 'version = "0.16.0"\n[project.scripts]\ncommons-x = "mod_x:main"\n')
    _touch(tmp_path, "mod_x.py", "def main(): ...\n")
    _touch(tmp_path, "CHANGELOG.md", "## [0.16.0] — 2026-11-02\n")

    assert doctor.main([str(tmp_path)]) == 1
