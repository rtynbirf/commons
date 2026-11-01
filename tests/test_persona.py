"""Приёмки SPEC-0010 (v0.1.0): персона и каналы — тело не требует ни одного канала.

Мандат человека: «я слепой, я глухой, я немой, у меня нет рук». Тело не обязано
владеть каналом — оно обязано не требовать его. Инвариант исполняется машиной,
а не декларируется: картинки не молчат (alt), ссылки названы словами, итоги
гейтов — словами и кодом возврата, аудио-артефактов нет, у excalidraw-карты
органов есть текстовый близнец, мандатный отчёт с посчитанными фактами на
месте — спека сдаёт свою кровь, дрейф спеки и отчёта невозможен.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIO_SUFFIXES = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".opus"}
MEANINGLESS_LINKS = {"here", "link", "сюда", "здесь", "ссылка", "тут"}


def _markdown_files() -> list[Path]:
    return [p for p in ROOT.rglob("*.md") if ".git" not in p.parts]


def _strip_code(text: str) -> str:
    """Убрать фенс-блоки и инлайн-код: документация правила — не нарушение правила."""
    text = re.sub(r"```[\s\S]*?```", "", text)
    return re.sub(r"`[^`]*`", "", text)


def test_markdown_images_have_alt() -> None:
    """П3: в маркдауне тела нет изображений без alt-текста."""
    bad = []
    for p in _markdown_files():
        for i, line in enumerate(_strip_code(p.read_text(encoding="utf-8")).splitlines(), 1):
            if re.search(r"!\[\s*\]\(", line):
                bad.append(f"{p.relative_to(ROOT)}:{i}")
    assert not bad, f"изображения без alt: {bad}"


def test_html_images_have_alt() -> None:
    """П3: HTML <img> без alt запрещён."""
    bad = []
    for p in _markdown_files():
        text = _strip_code(p.read_text(encoding="utf-8"))
        for m in re.finditer(r"<img\b[^>]*>", text):
            if "alt=" not in m.group(0):
                bad.append(p.relative_to(ROOT).as_posix())
    assert not bad, f"<img> без alt: {bad}"


def test_organ_map_has_text_twin() -> None:
    """П3: карта органов существует в двух формах — excalidraw и слова."""
    excal = ROOT / "docs" / "organ-map.excalidraw"
    twin = ROOT / "docs" / "organ-map.md"
    assert excal.is_file() and excal.stat().st_size > 0, "нет excalidraw-карты"
    assert twin.is_file() and len(twin.read_text(encoding="utf-8").split()) >= 50, (
        "текстовый близнец карты органов отсутствует или слишком беден"
    )


def test_links_are_named() -> None:
    """П6: ссылка называется словами, а не «сюда»/«here»."""
    bad = []
    for p in _markdown_files():
        for i, line in enumerate(_strip_code(p.read_text(encoding="utf-8")).splitlines(), 1):
            for m in re.finditer(r"\[([^\]]*)\]\(", line):
                if m.group(1).strip().lower() in MEANINGLESS_LINKS:
                    bad.append(f"{p.relative_to(ROOT)}:{i}")
    assert not bad, f"безымянные ссылки: {bad}"


def test_no_audio_artifacts() -> None:
    """П5: тело молчит — аудио-артефактов нет ни в чём."""
    audio = [
        p.relative_to(ROOT).as_posix()
        for p in ROOT.rglob("*")
        if p.is_file() and p.suffix.lower() in AUDIO_SUFFIXES and ".git" not in p.parts
    ]
    assert not audio, f"аудио-артефакты: {audio}"


def test_gate_summaries_are_words() -> None:
    """П4: итог каждого гейта — словами и кодом возврата, не цветом."""
    gates = {
        "immune/barrier.py": ("IMMUNE:", "ok, "),
        "immune/donation.py": ("TRANSPLANT:", "ok, "),
        "pipeline/check.py": ("PIPELINE:", "ok, "),
        "openclaw/check.py": ("POLICY:", "ok, "),
    }
    missing = []
    for rel, markers in gates.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                missing.append(f"{rel}: нет '{marker}'")
    assert not missing, missing


def test_persona_report_carries_the_facts() -> None:
    """Спека сдаёт свою кровь: посчитанные факты Келлер в отчёте волны."""
    report = (ROOT / "runs" / "2026-11-02-persona" / "report.md").read_text(encoding="utf-8")
    for fact in ("32 115", "578", "1.80%", "12 книг", "03.03.1887", "05.04.1887"):
        assert fact in report, f"в мандатном отчёте нет факта: {fact}"


def test_spec_0010_exists_and_is_declared() -> None:
    """Спека раньше кода: SPEC-0010 существует, шапка начинается со «Статус:»."""
    spec = (ROOT / "specs" / "SPEC-0010-persona.md").read_text(encoding="utf-8")
    assert spec.startswith("# SPEC-0010")
    assert re.search(r"^Статус:", spec, re.M), "Статус: — в начале строки (гейт CI validate)"
