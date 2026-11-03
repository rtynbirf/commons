"""Приёмка волны №26 — Ф-0' «гигиена дисциплины» (docs/TZ.md, ТЗ-0.1…ТЗ-0.5).

ТЗ-0.1 — Landlock: вторая независимая проба живым syscall'ом 444, факт в крови
прогона ``runs/2026-11-03-wave26-f0-hygiene/``, SPEC-0002 п.11 обновлён честно.
ТЗ-0.2 — W-0034: гейт дрейфа аксиом — doctor сверяет реестр A01–A25
(``docs/axioms.yaml``) против живых текстов дома; дрейф — красное.
ТЗ-0.3 — W-0030: гейт «поведение без спеки» — правка ``blood/``, ``synapse/``,
``brainstem/`` без правки ``specs/`` краснит коммит (fail-closed без git).
ТЗ-0.4 — W-0036: ADR-0015 «матрица приоритета законов» — конфликт
разрешается по-записанному, порядок назван заранее.
ТЗ-0.5 — W-0031: PIDLock против зомби-владельца и переиспользования PID
(гипотеза F-12 коллег): сначала живой замер, потом стемпинг стартовым
временем процесса (поле 22 /proc/<pid>/stat).
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from blood.journal import verify
from blood.pidlock import LockHeld, PIDLock

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "doctor.py"
RUN_DIR = REPO_ROOT / "runs" / "2026-11-03-wave26-f0-hygiene"


def _doctor():
    """Доктор загружается на каждый вызов: гейта ещё нет — AttributeError
    красит приёмку честно (красный прогон на нетронутом коде)."""
    spec = importlib.util.spec_from_file_location("doctor_wave26", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["doctor_wave26"] = module
    spec.loader.exec_module(module)
    return module


# --- ТЗ-0.2: W-0034, гейт дрейфа аксиом ---


def _axioms() -> dict:
    return yaml.safe_load((REPO_ROOT / "docs" / "axioms.yaml").read_text(encoding="utf-8"))


def test_axioms_registry_covers_all_25() -> None:
    registry = _axioms()
    ids = [row["id"] for row in registry["axioms"]]
    assert ids == [f"A{i:02d}" for i in range(1, 26)], "реестр обязан покрывать A01–A25 без пропусков и дублей"
    allowed = {"СЛУЖЕНО", "PASS", "ЧАСТИЧНО", "НЕ СЛУЖЕНО", "СНЯТО"}
    assert all(row["status"] in allowed for row in registry["axioms"])


def test_axioms_red_rows_carry_todo_and_adr() -> None:
    for row in _axioms()["axioms"]:
        if row["status"] in ("ЧАСТИЧНО", "НЕ СЛУЖЕНО"):
            assert str(row.get("todo", "")).startswith("ТЗ-"), f"{row['id']}: красная строка без пункта ТЗ"
        if row["status"] == "СНЯТО":
            assert (REPO_ROOT / row["adr"]).exists(), f"{row['id']}: снятая строка без живого ADR"


def test_axioms_gate_green_on_house() -> None:
    ok, fleas = _doctor().check_axioms(REPO_ROOT)
    assert fleas == [], "гейт дрейфа аксиом красен на живом доме — книги разошлись"
    assert ok > 0


def test_axioms_gate_red_on_drifted_marker(tmp_path: Path) -> None:
    """Дрейф: свидетель жив, но маркер служения из текста исчез — красное."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_witness.py").write_text("# маркер служения выветрился\n", encoding="utf-8")
    (docs / "axioms.yaml").write_text(
        yaml.safe_dump(
            {
                "axioms": [
                    {
                        "id": "A01",
                        "title": "повторная доставка",
                        "status": "СЛУЖЕНО",
                        "witness": "tests/test_witness.py",
                        "marker": "ЩАМПУР-СЛУЖЕНИЯ",
                    }
                ]
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    ok, fleas = _doctor().check_axioms(tmp_path)
    assert any("дрейф" in flea for flea in fleas), fleas


def test_axioms_gate_red_on_dead_witness(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "axioms.yaml").write_text(
        yaml.safe_dump(
            {
                "axioms": [
                    {
                        "id": "A01",
                        "status": "СЛУЖЕНО",
                        "witness": "tests/уволен.py",
                        "marker": "x",
                    }
                ]
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    ok, fleas = _doctor().check_axioms(tmp_path)
    assert any("A01" in flea and "свидетел" in flea for flea in fleas), fleas


def test_axioms_gate_red_on_orphan_reference(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "axioms.yaml").write_text(yaml.safe_dump({"axioms": []}, allow_unicode=True), encoding="utf-8")
    (docs / "note.md").write_text("Служено A99 и A42!\n", encoding="utf-8")
    ok, fleas = _doctor().check_axioms(tmp_path)
    assert any("A99" in flea and "сирот" in flea for flea in fleas), fleas


def test_axioms_gate_red_without_registry(tmp_path: Path) -> None:
    ok, fleas = _doctor().check_axioms(tmp_path)
    assert fleas, "нет реестра — fail-closed, тишина гейта недопустима"


# --- ТЗ-0.3: W-0030, гейт «поведение без спеки» ---


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _house(tmp_path: Path) -> Path:
    root = tmp_path / "house"
    (root / "blood").mkdir(parents=True)
    (root / "specs").mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "house@example")
    _git(root, "config", "user.name", "house")
    _commit(root, "base")
    return root


def _commit(root: Path, message: str) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--allow-empty", "-m", message)


def test_doctor_has_two_new_gates() -> None:
    names = [name for name, _ in _doctor().GATES]
    assert "axioms" in names and "spec-first" in names


def test_spec_first_green_on_books_only(tmp_path: Path) -> None:
    root = _house(tmp_path)
    (root / "README.md").write_text("книги\n", encoding="utf-8")
    _commit(root, "chore(book)")
    ok, fleas = _doctor().check_spec_first(root)
    assert fleas == [], fleas


def test_spec_first_red_on_code_without_spec(tmp_path: Path) -> None:
    root = _house(tmp_path)
    (root / "blood" / "new.py").write_text("X = 1\n", encoding="utf-8")
    _commit(root, "feat: тиходём")
    ok, fleas = _doctor().check_spec_first(root)
    assert any("спека раньше кода" in flea for flea in fleas), fleas


def test_spec_first_green_with_spec_in_same_commit(tmp_path: Path) -> None:
    root = _house(tmp_path)
    (root / "blood" / "new.py").write_text("X = 1\n", encoding="utf-8")
    (root / "specs" / "SPEC-0003-x.md").write_text("# спека догнала\n", encoding="utf-8")
    _commit(root, "feat: спека раньше кода")
    ok, fleas = _doctor().check_spec_first(root)
    assert fleas == [], fleas


def test_spec_first_not_applicable_without_git(tmp_path: Path) -> None:
    """Дереву без истории нечего судить: гейт неприменим (не «чист», а «нет HEAD»)."""
    ok, fleas = _doctor().check_spec_first(tmp_path)
    assert fleas == [], fleas


def test_spec_first_fail_closed_on_broken_git(tmp_path: Path) -> None:
    """.git есть, git сломан — непроверяемое ≠ чистое (fail-closed)."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "blood").mkdir()
    (tmp_path / "blood" / "x.py").touch()
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/нет\n", encoding="utf-8")
    ok, fleas = _doctor().check_spec_first(tmp_path)
    assert fleas, "битый git обязан красить (fail-closed)"


# --- ТЗ-0.4: W-0036, ADR-0015 матрица приоритета законов ---


def _adr_0015() -> str:
    return (REPO_ROOT / "docs" / "adr" / "ADR-0015-law-priority.md").read_text(encoding="utf-8")


def test_adr_0015_priority_order_machine_readable() -> None:
    text = _adr_0015()
    block = text.split("```yaml", 1)[1].split("```", 1)[0]
    data = yaml.safe_load(block)
    ladder = data["law_priority"]
    joined = " ".join(ladder).lower()
    positions = [
        joined.index("воля человека"),
        joined.index("тишин"),
        joined.index("бюджет"),
        joined.index("план"),
        joined.index("такт"),
    ]
    assert positions == sorted(positions), f"порядок нарушен: {ladder}"


def test_adr_0015_records_named_conflicts() -> None:
    text = _adr_0015()
    assert "выметани" in text and "вещественн" in text, "случай стыка 0.36.1 не разобран"
    assert "upstream" in text and "тест" in text, "случай «upstream против теста отключения» не разобран"


def test_specs_reference_adr_0015() -> None:
    assert "ADR-0015" in (REPO_ROOT / "specs" / "SPEC-0004-pid1.md").read_text(encoding="utf-8")


# --- ТЗ-0.5: W-0031, PIDLock против зомби-владельца (F-12) ---


def _stat_fields(pid: int) -> list[str] | None:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    return raw.rpartition(")")[2].split()


def _spawn_zombie() -> subprocess.Popen:
    """Ребёнок, которого родитель не пожинает: живой pid, мёртвый процесс."""
    child = subprocess.Popen([sys.executable, "-c", "import os; os._exit(0)"])
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        fields = _stat_fields(child.pid)
        if fields and fields[0] == "Z":
            return child
        time.sleep(0.02)
    child.wait()
    pytest.fail("зомби не случился — модель исполнения пожинает детей сама")


def test_lock_file_carries_start_time(tmp_path: Path) -> None:
    lock = PIDLock(tmp_path / ".lock")
    lock.acquire()
    data = json.loads((tmp_path / ".lock").read_text(encoding="utf-8"))
    assert "start_time" in data, "lock не несёт стартовое время — переиспользование PID неразличимо"
    lock.release()


@pytest.mark.skipif(sys.platform != "linux", reason="живая зомби-проба — Linux /proc")
def test_zombie_owner_replaced(tmp_path: Path) -> None:
    """Гипотеза F-12 живьём: зомби-владелец держал lock, будучи мёртвым."""
    child = _spawn_zombie()
    try:
        fields = _stat_fields(child.pid)
        assert fields and fields[0] == "Z"
        zstart = fields[19]  # поле 22 файла stat: starttime после comm
        (tmp_path / ".lock").write_text(
            json.dumps({"pid": child.pid, "start_time": zstart, "ts": "2026-11-03T00:00:00+00:00"}),
            encoding="utf-8",
        )
        lock = PIDLock(tmp_path / ".lock")
        assert lock.acquire() == os.getpid(), "зомби держит тело — тело заперто за мёртвым"
    finally:
        child.wait()


@pytest.mark.skipif(sys.platform != "linux", reason="живая зомби-проба — Linux /proc")
def test_zombie_replaced_even_in_old_lock_format(tmp_path: Path) -> None:
    """Старый lock без стемпинга: зомби всё равно ловится состоянием Z."""
    child = _spawn_zombie()
    try:
        (tmp_path / ".lock").write_text(
            json.dumps({"pid": child.pid, "ts": "2026-11-03T00:00:00+00:00"}),
            encoding="utf-8",
        )
        lock = PIDLock(tmp_path / ".lock")
        assert lock.acquire() == os.getpid(), "старый формат — не индульгенция для зомби"
    finally:
        child.wait()


def test_reused_pid_replaced(tmp_path: Path) -> None:
    """Переиспользование PID: живой чужак со стартовым временем не владельца."""
    (tmp_path / ".lock").write_text(
        json.dumps({"pid": os.getpid(), "start_time": "1", "ts": "2026-11-03T00:00:00+00:00"}),
        encoding="utf-8",
    )
    lock = PIDLock(tmp_path / ".lock")
    assert lock.acquire() == os.getpid(), "чужак с чужим стартовым временем держит тело"


def test_live_owner_with_matching_stamp_holds(tmp_path: Path) -> None:
    fields = _stat_fields(os.getpid())
    assert fields, "/proc недоступен — приёмка неприменима"
    (tmp_path / ".lock").write_text(
        json.dumps({"pid": os.getpid(), "start_time": fields[19], "ts": "now"}),
        encoding="utf-8",
    )
    with pytest.raises(LockHeld):
        PIDLock(tmp_path / ".lock").acquire()


def test_no_proc_falls_back_honestly(tmp_path: Path) -> None:
    """/proc нет (чужая граница): kill-семантика, граница названа, не скрыта."""
    dead = subprocess.Popen(["true"])
    dead.wait()
    (tmp_path / ".lock").write_text(json.dumps({"pid": dead.pid, "start_time": None}), encoding="utf-8")
    lock = PIDLock(tmp_path / ".lock", proc_root=str(tmp_path / "нет-proc"))
    assert lock.acquire() == os.getpid()
    lock.release()
    (tmp_path / ".lock").write_text(json.dumps({"pid": os.getpid(), "start_time": None}), encoding="utf-8")
    with pytest.raises(LockHeld):
        PIDLock(tmp_path / ".lock", proc_root=str(tmp_path / "нет-proc")).acquire()


def test_spec_0004_names_zombie_and_start_time() -> None:
    text = (REPO_ROOT / "specs" / "SPEC-0004-pid1.md").read_text(encoding="utf-8")
    assert "зомби" in text and "стартовое время" in text, "спека не догнала живой код"


# --- ТЗ-0.1: Landlock, вторая независимая проба — артефакты прогона ---


def test_wave26_run_artifacts_sealed() -> None:
    for name in ("run.py", "blood.jsonl", "report.md"):
        assert (RUN_DIR / name).exists(), f"артефакт живого прогона отсутствует: {name}"
    report = verify(RUN_DIR / "blood.jsonl")
    assert report["gaps"] == [] and not report.get("content_gaps"), "кровь прогона не заверена"
    assert report["chained"] and report["hashed"], "кровь прогона обязана быть chained + hashed"
    anchors = (
        (REPO_ROOT / "blood" / "anchors.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    mine = [json.loads(line) for line in anchors if line.strip()]
    mine = [a for a in mine if a.get("file") == "runs/2026-11-03-wave26-f0-hygiene/blood.jsonl"]
    assert mine, "кровь прогона не опечатана якорем"
    latest = mine[-1]
    report_with_anchor = verify(RUN_DIR / "blood.jsonl", anchor=latest)
    assert report_with_anchor["events"] >= latest["events"], "якорь помнит больше, чем живёт — усечение"
    assert not report_with_anchor.get("content_gaps")


def test_landlock_second_probe_named_in_report() -> None:
    text = (RUN_DIR / "report.md").read_text(encoding="utf-8")
    assert "ENOSYS" in text and "landlock" in text.lower(), "проба не названа честно"
    assert "волна №26" in text.lower()


def test_ci_gives_the_gate_its_parent_commit() -> None:
    """Урок живого CI (6ac04a8): shallow-клон (depth: 1) оставлял гейт
    spec-first fail-closed красным — checkout джоб с доктором и полным
    сюитом обязан нести родителя коммита (fetch-depth: 2)."""
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    weekly = (REPO_ROOT / ".github" / "workflows" / "fleas.yml").read_text(encoding="utf-8")
    assert ci.count("fetch-depth: 2") >= 2, "джобы hygiene и core обязаны давать родителя коммита"
    assert "fetch-depth: 2" in weekly, "недельный свип обязан давать родителя коммита"
