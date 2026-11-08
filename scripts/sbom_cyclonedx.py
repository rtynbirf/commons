#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CycloneDX-подобный SBOM дома COMMONS — только stdlib, детерминированный.

ПРЕДЛОЖЕНИЕ-38 (issue #12): sbom.json на каждый релиз. Формат — CycloneDX 1.5
(структура JSON: bomFormat, specVersion, serialNumber, metadata, components;
валидна схемой https://cyclonedx.org/schema/bom-1.5.schema.json).

Детерминизм (дом сильнее формата):
  - часов нет: timestamp не пишется (опционален в 1.5); --timestamp задаёт его явно;
  - serialNumber = UUIDv5 от имени репо + sha коммита (никаких случайных UUID4);
  - components отсортированы лексикографически по пути (git ls-files | sort);
  - json.dumps(..., sort_keys=True, ensure_ascii=False, indent=1) + "\\n" в конце.

Хеши — sha256 по живым байтам рабочих файлов (git ls-files). Лицензия дома —
Apache-2.0 (ADR-0003, REUSE.toml — канон лицензирования, ADR-0020).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path

REPO_NAME = "commons"
REPO_URL = "https://github.com/rtynbirf/commons"
LICENSE_ID = "Apache-2.0"


def sh(args: list[str], cwd: Path) -> str:
    out = subprocess.run(args, cwd=cwd, capture_output=True, check=True, text=True)
    return out.stdout


def git_files(root: Path) -> list[str]:
    """Отслеживаемые git-ом файлы, отсортированные (детерминизм важнее скорости)."""
    lines = sh(["git", "ls-files", "-z"], cwd=root).split("\0")
    return sorted(p for p in lines if p)


def git_head(root: Path) -> str:
    return sh(["git", "rev-parse", "HEAD"], cwd=root).strip()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def component_for(rel: str, root: Path) -> dict:
    return {
        "type": "file",
        "name": rel,
        "hashes": [{"alg": "SHA-256", "content": sha256_file(root / rel)}],
    }


def build_bom(root: Path, timestamp: str | None = None) -> dict:
    commit = git_head(root)
    serial = uuid.uuid5(uuid.NAMESPACE_URL, f"{REPO_URL}@{commit}")
    files = git_files(root)
    bom: dict = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "component": {
                "bom-ref": f"application:{REPO_NAME}",
                "type": "application",
                "name": REPO_NAME,
                "version": commit[:12],
                "licenses": [{"license": {"id": LICENSE_ID}}],
                "properties": [
                    {"name": "commons:repository", "value": REPO_URL},
                    {"name": "commons:commit", "value": commit},
                    {"name": "commons:license-canon", "value": "REUSE.toml (ADR-0003, ADR-0020)"},
                    {"name": "commons:determinism", "value": "no clock; uuid5(commit); sorted paths"},
                ],
            },
            "tools": [
                {"vendor": "rtynbirf", "name": "sbom_cyclonedx.py", "version": "1.0.0"}
            ],
        },
        "components": [component_for(rel, root) for rel in files],
    }
    if timestamp:
        bom["metadata"]["timestamp"] = timestamp
    return bom


def render(bom: dict) -> bytes:
    return (json.dumps(bom, sort_keys=True, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CycloneDX-подобный SBOM (stdlib, детерминированный)")
    ap.add_argument("--root", type=Path, default=Path("."), help="корень git-дерева (по умолчанию cwd)")
    ap.add_argument("--output", type=Path, default=None, help="куда писать sbom.json (по умолчанию stdout)")
    ap.add_argument("--timestamp", default=None, help="явный ISO-8601 timestamp (иначе поле опущено)")
    args = ap.parse_args(argv)

    root = args.root.resolve()
    if not (root / ".git").exists() and not (root / "LICENSE").exists():
        print(f"FAIL: {root} не похож на корень репо", file=sys.stderr)
        return 2

    bom = build_bom(root, timestamp=args.timestamp)
    data = render(bom)
    if args.output:
        args.output.write_bytes(data)
        n = len(bom["components"])
        print(f"OK: sbom записан: {args.output} (components: {n})")
    else:
        sys.stdout.buffer.write(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
