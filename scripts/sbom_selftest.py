#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Selftest SBOM-генератора (ПРЕДЛОЖЕНИЕ-38, issue #12) — только stdlib.

Приёмка машинная:
  1. двойная сборка подряд = байт-идентичный sbom.json (детерминизм);
  2. структурная валидность CycloneDX 1.5: bomFormat/specVersion/serialNumber
     (URN UUID), components — массив с type=file и SHA-256 хешами;
  3. полнота: множество компонентов == множество файлов `git ls-files`;
  4. честность хешей: выборочная (и полная по флагу --full) сверка sha256
     с живыми байтами файлов.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sbom_cyclonedx as sb  # noqa: E402


def fail(msg: str) -> int:
    print(f"SELFTEST FAIL: {msg}")
    return 1


def run(root: Path, out: Path) -> bytes:
    rc = sb.main(["--root", str(root), "--output", str(out)])
    assert rc == 0, f"generator exit {rc}"
    return out.read_bytes()


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else HERE.parent
    full = "--full" in argv

    with tempfile.TemporaryDirectory() as td:
        a, b = Path(td) / "a.json", Path(td) / "b.json"
        data_a = run(root, a)
        data_b = run(root, b)
        if data_a != data_b:
            return fail("двойная сборка не байт-идентична")
        print("PASS: двойная сборка байт-идентична")

        bom = json.loads(data_a)
        if bom.get("bomFormat") != "CycloneDX" or bom.get("specVersion") != "1.5":
            return fail("bomFormat/specVersion не CycloneDX 1.5")
        serial = bom.get("serialNumber", "")
        if not serial.startswith("urn:uuid:"):
            return fail("serialNumber не urn:uuid")
        try:
            uuid.UUID(serial[len("urn:uuid:"):])
        except ValueError:
            return fail("serialNumber не UUID")
        print("PASS: структура CycloneDX 1.5 валидна (serialNumber = URN UUID)")

        files = sb.git_files(root)
        names = [c.get("name") for c in bom.get("components", [])]
        if names != sorted(files):
            return fail("components != git ls-files (или не отсортированы)")
        for c in bom["components"]:
            if c.get("type") != "file" or not c.get("hashes"):
                return fail(f"компонент без type=file/хешей: {c.get('name')}")
        print(f"PASS: полнота — {len(names)} файлов, отсортированы, все с SHA-256")

        meta = bom.get("metadata", {}).get("component", {})
        if meta.get("name") != "commons" or not meta.get("version"):
            return fail("metadata.component без имени/версии-коммита")
        commit = sb.git_head(root)
        if not meta["version"].startswith(commit[:12]):
            return fail("metadata.component.version != git HEAD")
        print("PASS: metadata привязан к коммиту")

        checked = 0
        for c in bom["components"]:
            if not full and checked >= 25:
                break
            digest = c["hashes"][0]["content"]
            actual = sb.sha256_file(root / c["name"])
            if digest != actual:
                return fail(f"хеш не совпал: {c['name']}")
            checked += 1
        print(f"PASS: sha256 сверены с живыми байтами ({checked} шт.)")

    print("SELFTEST PASS: sbom детерминирован, валиден, полон, хеши честные")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
