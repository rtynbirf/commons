"""Приёмка автопортрета-2: excalidraw-карта органов (docs/organ-map.excalidraw).

Карта — AUTO-GENERATED артефакт scripts/organ_map.py: обязана существовать,
быть валидным excalidraw-JSON, покрывать весь реестр органов и быть
детерминированной (два запуска — байт-в-байт одинаковый файл).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "organ_map.py"
ARTIFACT = REPO_ROOT / "docs" / "organ-map.excalidraw"
REGISTRY = REPO_ROOT / "organs" / "registry.yaml"


def _document() -> dict:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def _texts(elements: list[dict]) -> str:
    """Все тексты текстовых элементов холста одним куском — для поиска подстрок."""
    return "\n".join(el.get("text", "") for el in elements if el.get("type") == "text")


def test_artifact_is_valid_excalidraw() -> None:
    assert ARTIFACT.exists(), "артефакт отсутствует — запусти python3 scripts/organ_map.py"
    doc = _document()
    for key in ("type", "version", "elements", "files"):
        assert key in doc, f"нет ключа {key} в excalidraw-документе"
    assert doc["type"] == "excalidraw"
    assert doc["version"] == 2
    assert isinstance(doc["elements"], list) and doc["elements"], "элементы пустые"
    assert doc["files"] == {}


def test_every_organ_name_is_on_the_map() -> None:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    blob = _texts(_document()["elements"])
    for organ in registry["organs"]:
        name = organ["repo"].rsplit("/", 1)[-1]
        assert name in blob, f"орган {name} из реестра не найден на карте"


def test_every_organ_license_is_on_the_map() -> None:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    blob = _texts(_document()["elements"])
    for organ in registry["organs"]:
        license_ = str(organ.get("license_pre", "?"))
        assert license_ in blob, f"лицензия {license_} ({organ['repo']}) не найдена на карте"


def test_generator_is_deterministic(tmp_path: Path) -> None:
    """Два запуска генератора на одном реестре — байт-в-байт одинаковые файлы."""
    first = tmp_path / "first.excalidraw"
    second = tmp_path / "second.excalidraw"
    for out in (first, second):
        subprocess.run(
            [sys.executable, str(SCRIPT), "--out", str(out)],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    assert first.read_bytes() == second.read_bytes(), "генератор недетерминирован"


def test_check_gate_passes() -> None:
    """Гейт свежести для CI: артефакт в дереве обязан совпадать с регенерацией."""
    proc = subprocess.run(
        [sys.executable, "scripts/organ_map.py", "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"гейт --check упал:\n{proc.stdout}\n{proc.stderr}"
    assert "OK" in proc.stdout
