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
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "doctor.py"

_spec = importlib.util.spec_from_file_location("doctor", SCRIPT)
doctor = importlib.util.module_from_spec(_spec)
sys.modules["doctor"] = doctor
_spec.loader.exec_module(doctor)

_report_spec = importlib.util.spec_from_file_location(
    "doctor_report", REPO_ROOT / "scripts" / "doctor_report.py"
)
doctor_report = importlib.util.module_from_spec(_report_spec)
sys.modules["doctor_report"] = doctor_report
_report_spec.loader.exec_module(doctor_report)


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

    assert len(fleas) == 4, fleas  # + README.en.md отсутствует (волна-6: fail-closed)
    assert any("CITATION.cff" in f for f in fleas)
    assert any("CHANGELOG.md" in f for f in fleas)
    assert any("README.md" in f for f in fleas)
    assert any("README.en.md" in f and "отсутствует" in f for f in fleas)
    assert ok == 1  # чист только pyproject


def test_version_sync_green(tmp_path: Path) -> None:
    _touch(tmp_path, "pyproject.toml", 'version = "0.16.0"\n')
    _touch(tmp_path, "CITATION.cff", "version: 0.16.0\n")
    _touch(tmp_path, "CHANGELOG.md", "## [0.16.0] — 2026-11-02\n")
    _touch(tmp_path, "README.md", "С 0.16.0 у организма есть гигиена дома.\n")
    _touch(tmp_path, "README.en.md", "Since 0.16.0 the house has hygiene.\n")

    ok, fleas = doctor.check_version_sync(tmp_path)

    assert (ok, fleas) == (5, [])


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


# --- гейты 0.18.0: конфликт-маркеры и числа-протухатели пополнены ---


def test_conflict_marker_is_caught(tmp_path: Path) -> None:
    _touch(
        tmp_path,
        "README.md",
        "<<<<<<< HEAD\nнаша строка\n=======\nчужая строка\n>>>>>>> feature\n",
    )

    ok, fleas = doctor.check_conflict_markers(tmp_path)

    assert ok == 0
    assert len(fleas) >= 2, fleas
    assert any("конфликт-маркер" in f for f in fleas)


def test_setext_underline_is_not_a_conflict(tmp_path: Path) -> None:
    # Подчёркивание заголовка (setext) ровно из семи `=` — легально,
    # пока рядом нет угловых маркеров.
    _touch(tmp_path, "docs/note.md", "Заголовок\n=======\n")

    ok, fleas = doctor.check_conflict_markers(tmp_path)

    assert (ok, fleas) == (1, [])


def test_practices_counter_is_caught(tmp_path: Path) -> None:
    # Урок llms.txt: «17 практик» при живых 18 — статика не счётчик.
    _touch(tmp_path, "README.md")
    _touch(tmp_path, "README.en.md")
    _touch(tmp_path, "CITATION.cff")
    _touch(tmp_path, "llms.txt", "- чеклист: 17 практик open-source и их статус\n")

    ok, fleas = doctor.check_no_stale_counts(tmp_path)

    assert ok == 3
    assert len(fleas) == 1, fleas
    assert "практик" in fleas[0]


def test_stage_badge_version_is_caught(tmp_path: Path) -> None:
    # Урок README: бейдж stage-0.15.0 при живых 0.17 — версия в бейдже гниёт.
    _touch(
        tmp_path,
        "README.md",
        "![stage](https://img.shields.io/badge/stage-0.15.0%20persona-orange)\n",
    )
    _touch(tmp_path, "README.en.md")
    _touch(tmp_path, "CITATION.cff")

    ok, fleas = doctor.check_no_stale_counts(tmp_path)

    assert ok == 2  # чисты только README.en.md и CITATION.cff
    assert len(fleas) == 1, fleas
    assert "stage" in fleas[0]


def test_missing_llms_does_not_crash_counts_gate(tmp_path: Path) -> None:
    # Фейковая карта без llms.txt: гейт терпит отсутствие, не падает.
    _touch(tmp_path, "README.md", "чисто\n")

    ok, fleas = doctor.check_no_stale_counts(tmp_path)

    assert (ok, fleas) == (1, [])


def test_headless_changelog_section_is_caught(tmp_path: Path) -> None:
    _touch(tmp_path, "CHANGELOG.md", "## [1.2.3]\n")

    ok, fleas = doctor.check_changelog_discipline(tmp_path)

    assert ok == 1
    assert len(fleas) == 1
    assert "без даты" in fleas[0]


# --- гейты 0.19.0: слепые зоны закрыты ---


def test_roadmap_stale_counter_is_caught(tmp_path: Path) -> None:
    # Волна-6: ROADMAP претендует на текущий статус — счётчики «N приёмок,
    # всего M» болеют там так же, как в README («29 приёмок, всего 215»
    # жили в ROADMAP при живых 350, потому что ROADMAP не стоял в зоне).
    _touch(tmp_path, "README.md")
    _touch(tmp_path, "README.en.md")
    _touch(tmp_path, "CITATION.cff")
    _touch(tmp_path, "ROADMAP.md", "- [x] дело (0.8.0): сделано; 29 приёмок, всего 215.\n")

    ok, fleas = doctor.check_no_stale_counts(tmp_path)

    assert ok == 3  # чисты README, README.en и CITATION — блоха одна, в ROADMAP
    assert len(fleas) == 1, fleas
    assert "ROADMAP.md" in fleas[0]
    assert "приёмок" in fleas[0]


def test_changelog_historical_numbers_are_not_fleas(tmp_path: Path) -> None:
    # Дизайн-граница жанров: CHANGELOG — журнал (Keep a Changelog),
    # исторические числа — его суть; гейт counts его не сканирует.
    _touch(tmp_path, "README.md")
    _touch(tmp_path, "README.en.md")
    _touch(tmp_path, "CITATION.cff")
    _touch(tmp_path, "CHANGELOG.md", "## [0.8.0] — 2026-11-01\n\n- бюджет; 29 приёмок, всего 215.\n")

    ok, fleas = doctor.check_no_stale_counts(tmp_path)

    assert (ok, fleas) == (3, [])


def test_missing_en_readme_is_caught_by_version_sync(tmp_path: Path) -> None:
    # Волна-6: en-история молча отстала на три релиза — теперь отсутствие
    # файла или непроговорённая версия в en — блоха, ru/en не расползаются.
    _touch(tmp_path, "pyproject.toml", 'version = "0.19.0"\n')
    _touch(tmp_path, "CITATION.cff", "version: 0.19.0\n")
    _touch(tmp_path, "CHANGELOG.md", "## [0.19.0] — 2026-11-02\n")
    _touch(tmp_path, "README.md", "С 0.19.0 гейты без слепых зон.\n")

    ok, fleas = doctor.check_version_sync(tmp_path)

    assert ok == 4  # чисты все, кроме en
    assert len(fleas) == 1, fleas
    assert "README.en.md" in fleas[0]


# --- гейты 0.20.0: реестр хотёлок ---


def test_want_orphan_is_caught(tmp_path: Path) -> None:
    # Волна-7: хотёлка, упомянутая вне реестра, — сирота; реестра нет — тоже блоха.
    _touch(tmp_path, "docs/note.md", "Служим хотёлке W-7777.\n")

    ok, fleas = doctor.check_want_refs(tmp_path)

    assert ok == 0
    assert len(fleas) == 2, fleas
    assert any("W-7777" in f for f in fleas)
    assert any("реестра нет" in f for f in fleas)


def test_want_without_status_is_caught(tmp_path: Path) -> None:
    # Хотёлка определена, но без «Статус:» — вердикта нет, значит обман.
    _touch(tmp_path, "docs/personas.md", "### W-0001 — рулить одной командой\nХочу: одна команда.\n")
    _touch(tmp_path, "ROADMAP.md", "служим W-0001\n")

    ok, fleas = doctor.check_want_refs(tmp_path)

    assert ok == 1  # ROADMAP чист — ссылка на определённую хотёлку
    assert len(fleas) == 1, fleas
    assert "W-0001" in fleas[0] and "Статус" in fleas[0]


def test_want_linked_and_stated_is_clean(tmp_path: Path) -> None:
    # Связанная хотёлка с вердиктом — дом чист: реестр + ссылающийся файл.
    _touch(
        tmp_path,
        "docs/personas.md",
        "### W-0001 — рулить одной командой\nХочу: одна команда.\nСтатус: СЛУЖЕНО — SPEC-0010.\n",
    )
    _touch(tmp_path, "ROADMAP.md", "служим W-0001 по SPEC-0010\n")

    ok, fleas = doctor.check_want_refs(tmp_path)

    assert (ok, fleas) == (2, [])


def test_want_backlog_block_without_headings_is_clean(tmp_path: Path) -> None:
    # Бэклог-блок реестра (хотёлки без ###-заголовков) не роняет гейт статусов:
    # вердикт обязателен для хозяина хотёлки, бэклог честен без формальностей.
    _touch(
        tmp_path,
        "docs/personas.md",
        "### W-0001 — дело\nХочу: дело.\nСтатус: СЛУЖЕНО — артефакт.\n\n## Честный бэклог\n\n- W-0002 — второе дело: ждёт хозяина.\n",
    )

    ok, fleas = doctor.check_want_refs(tmp_path)

    assert (ok, fleas) == (1, [])


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


def test_doctor_cli_reads_given_root(tmp_path: Path) -> None:
    # Волна-6: CLI обязан читать указанную карту, а не молча родной дом —
    # инъекция блохи в копию дома через `doctor.py /путь` обязана краснеть.
    import subprocess

    _touch(tmp_path, "README.md", "Всего 294 приёмок.\n")
    _touch(tmp_path, "README.en.md")
    _touch(tmp_path, "CITATION.cff")

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert proc.returncode == 1, proc.stdout
    assert "BLOHA" in proc.stdout
    assert "294 приём" in proc.stdout


def test_weekly_sweep_is_scheduled() -> None:
    # Обещание «на автомате пахать» приговорено приёмкой: свип существует,
    # он по расписанию, в нём доктор и внешние ссылки (lychee).
    fleas_wf = (REPO_ROOT / ".github" / "workflows" / "fleas.yml").read_text(encoding="utf-8")

    assert "schedule:" in fleas_wf, "свип не по расписанию — ссылки умирают сами, без пушей"
    assert "cron:" in fleas_wf, "cron свипа не задан"
    assert "scripts/doctor.py" in fleas_wf, "доктор не в свипе"
    assert "lychee" in fleas_wf, "внешние ссылки не проверяются свипом"
    # Право — минимальное (Scorecard Token-Permissions), как и во всём доме.
    assert "contents: read" in fleas_wf


# --- гейты 0.23.0: секреты, память воротов, hardening ---


def _fake_token() -> str:
    # Урок волны-8 выдержан: сырой пример блохи в статике — сам блоха.
    # Пример строится в рантайме — приёмка не кормит гейт собственным ядом.
    return "ghp_" + "4f9a" * 9


def test_github_token_is_caught_and_masked(tmp_path: Path) -> None:
    token = _fake_token()
    _touch(tmp_path, "README.md", f"ключ в стенах: {token}\n")

    ok, fleas = doctor.check_no_secrets(tmp_path)

    assert ok == 0
    assert len(fleas) == 1, fleas
    assert "GitHub PAT" in fleas[0]
    assert token[:8] in fleas[0], "маска обязана вести к месту блохи"
    assert token not in "".join(fleas), "ловец не размножает пойманное: секрет не печатается"


def test_private_key_is_caught(tmp_path: Path) -> None:
    # Маркер строится в рантайме (урок волны-8 живьём): пример блохи
    # в статике — сам блоха; песочница и гейт согласны: литерала не живёт.
    marker = "-----BEGIN RSA " + "PRIVATE" + " KEY" + "-----"
    _touch(tmp_path, "docs/key.md", marker + "\n")

    ok, fleas = doctor.check_no_secrets(tmp_path)

    assert ok == 0
    assert len(fleas) == 1, fleas
    assert "приватный ключ" in fleas[0]


def test_secret_in_runs_is_caught_poison_is_not_history(tmp_path: Path) -> None:
    # Кровь не переписывается — но секрет не кровь, а яд: runs/ в зоне гейта.
    _touch(tmp_path, "runs/2026-11-02-x/blood.jsonl", '{"payload": "' + _fake_token() + '"}\n')

    ok, fleas = doctor.check_no_secrets(tmp_path)

    assert ok == 0
    assert len(fleas) == 1, fleas
    assert "runs/" in fleas[0]


def test_secretfree_house_is_clean(tmp_path: Path) -> None:
    # Ловцы в статике — не секрет: паттерн формой не подставлен.
    _touch(tmp_path, "README.md", "ключи описаны словами, а не формой\n")
    _touch(tmp_path, "scripts/law.py", 'PATTERN = r"\\bAKIA[0-9A-Z]{16}\\b"  # ловец, не секрет\n')

    ok, fleas = doctor.check_no_secrets(tmp_path)

    assert (ok, fleas) == (2, [])


def _clean_house(root: Path) -> None:
    """Минимальный зелёный дом: все 13 гейтов чисты (волна №26: +axioms, +spec-first).
    Такт аудита (0.48.2): гейт axioms держит порог DoD — зелёный дом несёт
    СЛУЖЕНО/PASS ≥ 20, красных ≤ 2, СНЯТО с живым ADR (как живой дом)."""
    _touch(root, "pyproject.toml", 'version = "0.23.0"\n[project.scripts]\ncommons-x = "mod_x:main"\n')
    _touch(root, "mod_x.py", "def main(): ...\n")
    _touch(root, "CITATION.cff", "version: 0.23.0\n")
    _touch(root, "CHANGELOG.md", "## [0.23.0] — 2026-11-02\n")
    _touch(root, "README.md", "Дом 0.23.0. Руки: commons-x\n")
    _touch(root, "README.en.md", "House 0.23.0.\n")
    _touch(root, "ROADMAP.md", "дело\n")
    _touch(root, "docs/personas.md", "### W-0001 — дело\nХочу: дело.\nСтатус: СЛУЖЕНО — артефакт.\n")
    _touch(root, "tests/test_witness.py", "маркер служения жив\n")
    _touch(root, "docs/adr/ADR-0001.md", "# ADR-0001 — снятие аксиомы\n")
    rows: list[str] = []
    for i in range(1, 26):
        if i == 2:  # СНЯТО — живой ADR обязателен (гейт axioms)
            rows.append('  - id: A02\n    title: "аксиома 02"\n    status: СНЯТО\n    adr: "docs/adr/ADR-0001.md"\n')
        elif i == 3:  # единственная красная — с пунктом ТЗ (порог ≤ 2)
            rows.append('  - id: A03\n    title: "аксиома 03"\n    status: НЕ СЛУЖЕНО\n    todo: "ТЗ-2.3"\n')
        else:  # 23 СЛУЖЕНО с живым свидетелем и маркером (порог ≥ 20)
            rows.append('  - id: A%02d\n    title: "аксиома %02d"\n    status: СЛУЖЕНО\n    witness: "tests/test_witness.py"\n    marker: "маркер служения"\n' % (i, i))
    _touch(root, "docs/axioms.yaml", f"axioms:\n{''.join(rows)}")


def test_doctor_json_report_is_machine_readable(tmp_path: Path, capsys) -> None:
    # W-0017: коллега-агент читает ворота без человека — отчёт парсится,
    # все гейты перечислены, зелёный дом даёт exit 0.
    _clean_house(tmp_path)

    code = doctor.main(["--json", str(tmp_path)])
    report = json.loads(capsys.readouterr().out)

    assert code == 0
    assert report["total_fleas"] == 0
    assert report["gates"][0]["gate"] == "counts"
    assert "secrets" in [g["gate"] for g in report["gates"]]


def test_doctor_json_reports_fleas_and_fails_closed(tmp_path: Path, capsys) -> None:
    _clean_house(tmp_path)
    _touch(tmp_path, "docs/note.md", f"утечка: {_fake_token()}\n")

    code = doctor.main(["--json", str(tmp_path)])

    report = json.loads(capsys.readouterr().out)
    assert code == 1
    assert report["total_fleas"] >= 1
    assert any("GitHub PAT" in f for g in report["gates"] for f in g["fleas"])


def test_doctor_report_renders_summary_table() -> None:
    table = doctor_report.render(
        {"gates": [{"gate": "counts", "ok": 3, "fleas": []}], "total_ok": 3, "total_fleas": 0}
    )

    assert "| counts | 3 | 0 |" in table
    assert "Итог: 3 ok, 0 failed" in table


def test_workflows_carry_memory_and_hardening() -> None:
    # Волна №9 такт 2: каждый прогон ворот оставляет след (json → артефакт
    # + summary) и не висит вечно (timeout); пин upload-artifact по SHA.
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    fleas_wf = (REPO_ROOT / ".github" / "workflows" / "fleas.yml").read_text(encoding="utf-8")

    for wf, name in ((ci, "ci.yml"), (fleas_wf, "fleas.yml")):
        assert "doctor-report.json" in wf, f"{name}: машиночитаемого следа нет"
        assert "GITHUB_STEP_SUMMARY" in wf, f"{name}: память воротов не в summary"
        assert "timeout-minutes" in wf, f"{name}: ворота без срока — висят вечно"
    assert "concurrency" in ci, "ci не отменяет устаревшие прогоны"
    assert re.search(r"upload-artifact@[0-9a-f]{40}", ci + fleas_wf), "upload-artifact не запинен по SHA"
