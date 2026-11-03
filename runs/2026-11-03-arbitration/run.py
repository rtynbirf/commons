# Живой прогон волны №25 — арбитраж, аудит и ревизия всего и вся.
# Директива Человека (2026-11-03): «СТОП ПРИОСТАНАВЛИВАЕМ УПЛОТНЕНИЕ СВЯЗЕЙ,
# НАЧИНАЕМ АРБИТРАЖ АУДИТ И РЕВИЗИЮ ВСЕГО И ВСЯ ДЕЛАЕМ ТЗ ДОРОЖНУЮ КАРТУ
# И ДОККУМЕНТЫ ПО ВСЕМУ ИМЕЮЩЕМУСЯ У НАС НА ДАННЫЙ МОМЕНТ».
# Ревизор не чинит: замеры в кровь, вердикты — в ARBITRATION.md и docs/TZ.md.
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, verify  # noqa: E402

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
TRACE = "wave25-arbitration"


def run_cmd(cmd: list[str], cwd: Path = REPO_ROOT, timeout: int = 600) -> str:
    out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return (out.stdout or "") + (out.stderr or "")


t0 = time.monotonic()

# Замер 1 — приёмки: полный прогон pytest.
pytest_out = run_cmd([sys.executable, "-m", "pytest", "tests/", "-q"])
m = re.search(r"(\d+) passed", pytest_out)
pytest_passed = int(m.group(1)) if m else None
pytest_failed = re.search(r"(\d+) failed", pytest_out) is not None

# Замер 2 — доктор: гигиена дома.
doctor_out = run_cmd([sys.executable, "scripts/doctor.py"])
md = re.search(r"DOCTOR:\s*(\d+) ok,\s*(\d+) failed", doctor_out)
doctor_ok = int(md.group(1)) if md else None
doctor_failed = int(md.group(2)) if md else None

# Замер 3 — донорский трек живым API (Ф-Д): состояние шести точек.
donor_points = [
    ("n8n-io/n8n-docs", "issues", "5689"),
    ("microsoft/markitdown", "issues", "2808"),
    ("microsoft/markitdown", "issues", "2810"),
    ("microsoft/markitdown", "issues", "2732"),
    ("langchain-ai/langchain", "issues", "41624"),
    ("langchain-ai/langchain", "pulls", "41632"),
    ("shadcn-ui/ui", "pulls", "12568"),
]
token = os.environ.get("GH_TOKEN", "")
donors: list[dict] = []
if token:
    for repo, kind, num in donor_points:
        url = f"https://api.github.com/repos/{repo}/{kind}/{num}"
        req = urllib.request.Request(url, headers={"Authorization": f"token {token}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                d = json.loads(resp.read().decode())
            donors.append({
                "point": f"{repo}#{num}",
                "state": d.get("state"),
                "merged": d.get("merged"),
                "comments": d.get("comments"),
                "updated_at": d.get("updated_at"),
            })
        except Exception as e:  # честный отказ, не выдумка
            donors.append({"point": f"{repo}#{num}", "error": str(e)[:120]})
else:
    donors.append({"error": "GH_TOKEN не задан — замер честно не сделан"})

# Замер 4 — реестры: релизы, хотёлки, приёмки, ADR, SPEC.
changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
releases = len(re.findall(r"^## \[", changelog, re.M))
personas = (REPO_ROOT / "docs/personas.md").read_text(encoding="utf-8")
wishes = len(set(re.findall(r"\bW-(\d{4})\b", personas)))
wishes_served = len(re.findall(r"Статус: СЛУЖЕНО", personas))
wishes_partial = len(re.findall(r"Статус: ЧАСТИЧНО", personas))
adr_count = len(list((REPO_ROOT / "docs/adr").glob("ADR-*.md")))
spec_count = len(list((REPO_ROOT / "specs").glob("SPEC-*.md")))
runs_count = len([p for p in (REPO_ROOT / "runs").iterdir() if p.is_dir()])
tests_total = sum(
    len(re.findall(r"^def test_", p.read_text(encoding="utf-8"), re.M))
    for p in (REPO_ROOT / "tests").glob("test_*.py")
)

seconds = round(time.monotonic() - t0, 1)

journal = Journal()
journal.attach(JOURNAL)

journal.append(make(
    event_type="boot",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "role": "волна №25 — арбитраж, аудит и ревизия всего и вся (директива Человека 2026-11-03)",
        "scope": "замеры дома; сверка реестров A/W; донорский трек живым API; ТЗ и дорожная карта — docs/TZ.md",
        "repo_base_commit": "3749287",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=seconds),
    idempotency_key="wave25-boot",
))

journal.append(make(
    event_type="act",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "pytest-full",
        "passed": pytest_passed,
        "failed": pytest_failed,
        "verdict": "приёмки живы" if pytest_passed and not pytest_failed else "приёмки красные",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
    idempotency_key="wave25-pytest",
))

journal.append(make(
    event_type="act",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "doctor-hygiene",
        "ok": doctor_ok,
        "failed": doctor_failed,
        "verdict": "дом чист" if doctor_failed == 0 else "доктор красный",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
    idempotency_key="wave25-doctor",
))

journal.append(make(
    event_type="act",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "donor-track-live-api",
        "points": donors,
        "law": "совет ≠ факт, факт = замер: состояния чужих очередей замерены, не вспомнены",
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
    idempotency_key="wave25-donors",
))

journal.append(make(
    event_type="act",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "act": "registries-sweep",
        "releases": releases,
        "wishes_total": wishes,
        "wishes_served": wishes_served,
        "wishes_partial": wishes_partial,
        "wishes_open": wishes - wishes_served - wishes_partial,
        "adrs": adr_count,
        "specs": spec_count,
        "run_catalogs": runs_count,
        "test_functions": tests_total,
    },
    cost=Cost(tokens_in=0, tokens_out=0, seconds=0.0),
    idempotency_key="wave25-registries",
))

journal.close()

print(json.dumps(verify(JOURNAL), ensure_ascii=False))
