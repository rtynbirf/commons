#!/usr/bin/env python3
"""Organ map: второй автопортрет организма — карта органов в excalidraw.

Читает живые реестры (organs/registry.yaml + synapse/mcp-manifest.yaml) и
генерирует docs/organ-map.excalidraw — открываемую в excalidraw карту органов:
колонка = система, карточка = прямоугольник с текстом «name · license · mode».
Органы, объявленные в манифесте синапсов, подсвечены голубым — они доступны телу.

Артефакт AUTO-GENERATED: ручные правки docs/organ-map.excalidraw запрещены —
правь реестры и перегенерируй. Файл детерминирован: сортировка систем и органов
по имени, id/seed элементов = sha1(метка), никакой временной метки в содержимом
(датировку делает git, не файл). Два запуска на одном реестре дают файл,
совпадающий байт-в-байт.

Запуск:   python3 scripts/organ_map.py
Гейт CI:  python3 scripts/organ_map.py --check   (exit 0 — карта свежая)
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "organs" / "registry.yaml"
MANIFEST = ROOT / "synapse" / "mcp-manifest.yaml"
DEFAULT_OUT = ROOT / "docs" / "organ-map.excalidraw"

SOURCE = "scripts/organ_map.py (COMMONS)"

# Русские названия систем — как в selfmap.py; незнакомый ключ печатается как есть.
SYSTEM_TITLES = {
    "genome": "Геном",
    "brainstem": "Ствол мозга",
    "synapse": "Синапсы",
    "blood": "Кровь",
    "metabolism": "Метаболизм",
    "memory": "Память",
    "senses": "Сенсорика",
    "effectors": "Эффекторы",
    "nerves_alt": "Нервные альтернативы",
    "glands": "Железы",
    "skin": "Кожа",
    "selfmap": "Самоописание",
    "remote": "Удалённость",
    "immune_knowledge": "Иммунитет (знания)",
    "substrate": "Субстрат",
    "reproduction": "Репродукция",
}

# Геометрия колонок/карточек (в пикселях excalidraw).
MARGIN = 48
COLUMN_WIDTH = 280
COLUMN_GAP = 56
CARD_HEIGHT = 52
CARD_GAP = 24
CARD_PAD = 14
SECTION_GAP = 44

TITLE_FONT = 28
SUBTITLE_FONT = 12
SECTION_FONT = 20
CARD_FONT = 14
LINE_HEIGHT = 1.25

WIRED_BG = "#a5d8ff"  # орган в манифесте синапсов — доступен телу
PLAIN_BG = "#ffffff"  # орган только в реестре
STROKE = "#1e1e1e"
WIRED_STROKE = "#1971c2"
SECTION_COLOR = "#364fc7"
TITLE_COLOR = "#1e1e1e"
SUBTITLE_COLOR = "#868e96"


def organ_name(organ: dict) -> str:
    """Имя органа — хвост repo (как в selfmap.py: 'ollama/ollama' -> 'ollama')."""
    return str(organ["repo"]).rsplit("/", 1)[-1]


def load_groups() -> list[tuple[str, list[dict]]]:
    """Реестр -> [(system, [organs...]), ...]; системы и органы отсортированы по имени."""
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    groups: dict[str, list[dict]] = {}
    for organ in registry.get("organs", []):
        groups.setdefault(str(organ.get("system", "?")), []).append(organ)
    return [(s, sorted(groups[s], key=organ_name)) for s in sorted(groups)]


def wired_names() -> set[str]:
    """Органы, объявленные в манифесте синапсов (для тела существуют только они)."""
    try:
        manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return set()
    return {str(o["name"]) for o in manifest.get("organs", [])}


def element_id(label: str) -> str:
    """id элемента = первые 16 hex sha1(метки) — детерминированный, без случайности."""
    return hashlib.sha1(label.encode("utf-8")).hexdigest()[:16]


def stable_int(label: str) -> int:
    """Детерминированный int32 из метки — вместо случайных seed/versionNonce."""
    return int(hashlib.sha1(("int:" + label).encode("utf-8")).hexdigest()[:8], 16)


def base_element(el_type: str, label: str, x: float, y: float, w: float, h: float) -> dict:
    """Минимально-валидный каркас элемента excalidraw (детерминированный)."""
    return {
        "id": element_id(label),
        "type": el_type,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "angle": 0,
        "strokeColor": STROKE,
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 1,
        "strokeStyle": "solid",
        "roughness": 1,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "roundness": None,
        "seed": stable_int(label),
        "version": 1,
        "versionNonce": stable_int("nonce:" + label),
        "isDeleted": False,
        "boundElements": None,
        "updated": 1,
        "link": None,
        "locked": False,
    }


def text_element(label: str, text: str, x: float, y: float, font_size: int, color: str) -> dict:
    """Свободный текст поверх холста (containerId: null — excalidraw это принимает)."""
    width = max(1.0, len(text) * font_size * 0.6)
    el = base_element("text", label, x, y, width, font_size * LINE_HEIGHT)
    el.update(
        {
            "strokeColor": color,
            "text": text,
            "fontSize": font_size,
            "fontFamily": 1,
            "textAlign": "left",
            "verticalAlign": "top",
            "containerId": None,
            "originalText": text,
            "lineHeight": LINE_HEIGHT,
        }
    )
    return el


def card_element(label: str, text: str, wired: bool, x: float, y: float) -> list[dict]:
    """Карточка органа: прямоугольник + текст «name · license · mode» поверх него."""
    bg = WIRED_BG if wired else PLAIN_BG
    rect = base_element("rectangle", label, x, y, COLUMN_WIDTH, CARD_HEIGHT)
    rect["backgroundColor"] = bg
    rect["strokeColor"] = WIRED_STROKE if wired else STROKE
    label_text = text_element(
        f"{label}:text", text, x + CARD_PAD, y + CARD_PAD, CARD_FONT, STROKE
    )
    label_text["width"] = COLUMN_WIDTH - 2 * CARD_PAD
    return [rect, label_text]


def build_elements(groups: list[tuple[str, list[dict]]], wired: set[str]) -> list[dict]:
    """Холст: заголовок, затем колонки по системам с карточками органов."""
    elements: list[dict] = [
        text_element("title", "COMMONS — карта органов", MARGIN, MARGIN, TITLE_FONT, TITLE_COLOR),
        text_element(
            "subtitle",
            "AUTO-GENERATED: python3 scripts/organ_map.py — править руками запрещено, правь реестры",
            MARGIN,
            MARGIN + TITLE_FONT * LINE_HEIGHT + 8,
            SUBTITLE_FONT,
            SUBTITLE_COLOR,
        ),
    ]
    top = MARGIN + TITLE_FONT * LINE_HEIGHT + SUBTITLE_FONT * LINE_HEIGHT + 24
    for column, (system, organs) in enumerate(groups):
        x = MARGIN + column * (COLUMN_WIDTH + COLUMN_GAP)
        title = SYSTEM_TITLES.get(system, system)
        elements.append(
            text_element(f"section:{system}", title, x, top, SECTION_FONT, SECTION_COLOR)
        )
        y = top + SECTION_GAP
        for organ in organs:
            name = organ_name(organ)
            license_ = str(organ.get("license_pre", "?"))
            mode = str(organ.get("mode", "?"))
            elements += card_element(
                f"card:{system}:{name}", f"{name} · {license_} · {mode}", name in wired, x, y
            )
            y += CARD_HEIGHT + CARD_GAP
    return elements


def build_document() -> dict:
    """Собрать excalidraw-документ целиком (детерминированный)."""
    groups = load_groups()
    wired = wired_names()
    return {
        "type": "excalidraw",
        "version": 2,
        "source": SOURCE,
        "elements": build_elements(groups, wired),
        "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None, "gridStep": 5},
        "files": {},
    }


def render_document() -> str:
    """Документ -> строка JSON (детерминированная побайтово)."""
    return json.dumps(build_document(), ensure_ascii=False, indent=2) + "\n"


def check(path: Path, rendered: str) -> int:
    """Гейт свежести: регенерированный файл обязан совпадать с существующим."""
    if not path.exists():
        print(f"FAIL: {path} не существует — запусти: python3 scripts/organ_map.py")
        return 1
    try:
        current = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"FAIL: {path} не читается: {exc}")
        return 1
    if current == rendered:
        print("OK: карта свежая")
        return 0
    diff = list(
        difflib.unified_diff(
            current.splitlines(), rendered.splitlines(), fromfile=str(path), tofile="<регенерация>"
        )
    )
    print(f"FAIL: {path} отличается от регенерации (строк diff: {len(diff)}):")
    for line in diff[:60]:
        print(line)
    if len(diff) > 60:
        print(f"... ещё {len(diff) - 60} строк")
    print("Регенерируй: python3 scripts/organ_map.py")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="COMMONS: карта органов в excalidraw из живого реестра (AUTO-GENERATED)."
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="куда писать артефакт")
    parser.add_argument("--check", action="store_true", help="гейт свежести: сравнить с регенерацией")
    args = parser.parse_args(argv)

    rendered = render_document()
    if args.check:
        return check(args.out, rendered)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(rendered, encoding="utf-8")
    groups = load_groups()
    total = sum(len(organs) for _, organs in groups)
    print(f"organ-map: {args.out} ({total} органов, {len(groups)} систем)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
