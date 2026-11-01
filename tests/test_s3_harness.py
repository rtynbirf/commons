"""Приёмка харнесса спайка S3: матрица офлайн, NO_SERVER, покрытие полей SPEC-0003."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MEASURE = REPO_ROOT / "spikes" / "s3-orchestration" / "measure.py"
SCHEMA = REPO_ROOT / "blood" / "envelope.schema.json"


def measure_module():
    """Импортирует spikes/s3-orchestration/measure.py по пути (спайк — не пакет)."""
    spec = importlib.util.spec_from_file_location("s3_harness_measure", MEASURE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_matrix_prints_verified_license_rows() -> None:
    result = subprocess.run(
        [sys.executable, "spikes/s3-orchestration/measure.py", "--matrix"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0
    assert "langflow" in result.stdout
    assert "n8n" in result.stdout
    assert "NOASSERTION" in result.stdout


def test_without_urls_prints_no_server_and_exits_2() -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("S3_")}
    result = subprocess.run(
        [sys.executable, "spikes/s3-orchestration/measure.py"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 2
    assert "NO_SERVER" in result.stdout


def test_trace_coverage_counts_spec_fields() -> None:
    measure = measure_module()
    full = {field: "x" for field in measure.REQUIRED_FIELDS}
    assert measure.trace_coverage(full) == (8, [])
    partial = {field: "x" for field in ("id", "ts", "type")}
    assert measure.trace_coverage(partial) == (
        3, sorted(set(measure.REQUIRED_FIELDS) - {"id", "ts", "type"}),
    )


def test_required_fields_come_from_schema_not_hardcode() -> None:
    measure = measure_module()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert list(measure.REQUIRED_FIELDS) == list(schema["required"])
    assert set(measure.REQUIRED_FIELDS) == {
        "id", "ts", "type", "source", "organ", "trace_id", "payload", "cost",
    }
