# Живой прогон волны №25 (0.44.0): законы при конфликте (W-0036, ADR-0016),
# гейт дрейфа аксиом (W-0034) и честный ADR транспорта (Ф-3.1, ADR-0017).
# Сцены: живой дом — гейт аксиом зелёный; дрейф матрицы — красный ловится;
# нечитаемая матрица — красный без суждения (fail-closed); живые конфликты
# законов разрешаются по-записанному; транспорт — только stdio данными.
# Органов в прогоне нет: волна о законах — кровь проливает сам дом.
from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, seal, verify  # noqa: E402

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
TRACE = "wave25-laws"

# Гейт доктора подгружается как файл (гейт — сценарий, не пакет).
_spec = importlib.util.spec_from_file_location("doctor", REPO_ROOT / "scripts" / "doctor.py")
_doctor = importlib.util.module_from_spec(_spec)
sys.modules["doctor"] = _doctor
_spec.loader.exec_module(_doctor)
check_axioms = _doctor.check_axioms

journal = Journal()
journal.attach(JOURNAL)

journal.append(make(
    event_type="boot",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "role": "волна №25 (0.44.0): матрица приоритета законов (W-0036, ADR-0016) + гейт дрейфа аксиом (W-0034) + честный ADR транспорта (Ф-3.1, ADR-0017)",
        "directive": "при конфликте законов порядок назван заранее, по-записанному; матрица — данные, ADR — вердикт, гейт — честность",
        "honesty": "органов в прогоне нет — волна о законах; кровь проливает сам дом (гейты и матрица)",
    },
    cost=Cost(),
))

data = yaml.safe_load((REPO_ROOT / "docs" / "axioms.yaml").read_text(encoding="utf-8"))
laws = [law["name"] for law in data["laws_priority"]]
rank = {name: i for i, name in enumerate(laws)}

# --- Сцена 1: живой дом — гейт аксиом зелёный (25/25) --------------------------
ok, fleas = check_axioms(REPO_ROOT)
assert ok == 25 and not fleas, fleas
journal.append(make(
    event_type="observe",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "step": 1,
        "scene": "живой дом: гейт аксиом зелёный",
        "result": "25 аксиом чисты, указатели живы, планы у открытых названы",
    },
    cost=Cost(),
))

# --- Сцена 2: дрейф матрицы — красный ловится на копии дома --------------------
with tempfile.TemporaryDirectory() as td:
    house = Path(td) / "house"
    shutil.copytree(REPO_ROOT, house, ignore=shutil.ignore_patterns("__pycache__", ".git", "*.pyc"))
    axioms_path = house / "docs" / "axioms.yaml"
    axioms_path.write_text(
        axioms_path.read_text(encoding="utf-8").replace("\n    verdict: pass", "\n    verdict: якобы-ок", 1),
        encoding="utf-8",
    )
    ok, fleas = check_axioms(house)
    assert ok == 24 and fleas and "чужой вердикт" in fleas[0], (ok, fleas)
journal.append(make(
    event_type="observe",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "step": 2,
        "scene": "дрейф матрицы: чужой вердикт пойман на копии дома",
        "result": "блоха названа вслух, не спрятана",
    },
    cost=Cost(),
))

# --- Сцена 3: нечитаемая матрица — красный без суждения (fail-closed) ----------
with tempfile.TemporaryDirectory() as td:
    house = Path(td) / "house"
    shutil.copytree(REPO_ROOT, house, ignore=shutil.ignore_patterns("__pycache__", ".git", "*.pyc"))
    (house / "docs" / "axioms.yaml").write_text("::: сломано :::\n", encoding="utf-8")
    ok, fleas = check_axioms(house)
    assert ok == 0 and fleas and "не читается" in fleas[0], (ok, fleas)
journal.append(make(
    event_type="observe",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "step": 3,
        "scene": "нечитаемая матрица: fail-closed",
        "result": "красный без суждения, а не «ну похоже на правду»",
    },
    cost=Cost(),
))

# --- Сцена 4: живые конфликты законов решаются по-записанному ------------------
conflicts = [
    ("выметание параллельной машины против сохранения пролитой крови", "кровь", "дисциплина"),
    ("тишина за окном против вечного ожидания ответа", "тождество", "время"),
    ("красивый код без спеки против спеки раньше кода", "дисциплина", "время"),
    ("выдать результат быстрее против честного отказа", "честность", "время"),
    ("сеть удобнее против тела без каналов", "безопасность", "время"),
]
for i, (case, a, b) in enumerate(conflicts, start=1):
    assert rank[a] < rank[b], f"{case}: матрица не решает ({a} vs {b})"
    journal.append(make(
        event_type="observe",
        source="brainstem",
        organ="self",
        trace_id=TRACE,
        payload={
            "step": 4,
            "scene": f"конфликт законов: {case}",
            "result": f"по матрице ADR-0016 побеждает «{a}» ({a} выше {b})",
        },
        cost=Cost(),
    ))

# --- Сцена 5: транспорт — только stdio данными ---------------------------------
manifest = yaml.safe_load((REPO_ROOT / "synapse" / "mcp-manifest.yaml").read_text(encoding="utf-8"))
assert manifest["transport_default"] == "stdio"
journal.append(make(
    event_type="observe",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "step": 5,
        "scene": "ADR-0017 «только stdio» данными",
        "result": "transport_default: stdio в живом манифесте; сетевой вызов тела — спека раньше кода",
    },
    cost=Cost(),
))

# --- Печать и сверка своей крови ------------------------------------------------
anchor = seal(JOURNAL)
report = verify(JOURNAL, anchor=anchor)
assert report["gaps"] == [] and report["content_gaps"] == [] and report["skipped"] == 0, report
envelopes = journal.by_trace(TRACE)
print(f"WAVE25: {len(envelopes)} конвертов, 0 гэпов, chained + hashed, опечатана якорем; "
      f"конфликтов разрешено по-записанному: {len(conflicts)}")
