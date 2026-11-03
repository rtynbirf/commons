"""Приёмки SPEC-0003 v0.5.0: цепочка prev_id (п.7) и реконструкция сессии (п.8).

Журнал — цепочка конвертов: каждый записанный конверт несёт prev_id предыдущего
конверта того же файла. Разрыв журнала (удаление, подмена, вставка) обнаруживается
при чтении — verify отчитывается гэпами, гематология красит файл. Сессия ствола
мозга полностью реконструируется по журналу: план, вызовы, наблюдения, вердикты,
остановки и полная цена трейса — resume из крови, без достраивания того, чего в
крови нет.
"""

from __future__ import annotations

import json
from pathlib import Path

from blood.envelope import Cost, make, new_trace_id
from blood.journal import Journal
from brainstem import Budget

from .conftest import step


# --- п.7: цепочка prev_id -----------------------------------------------------


def _write_envelopes(path: Path, events: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n",
        encoding="utf-8",
    )


def test_journal_chains_prev_id(tmp_path: Path) -> None:
    path = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.attach(path)
    first = journal.append(make("plan", "brainstem", "self", "t1", {"index": 0}))
    second = journal.append(make("act", "brainstem", "self", "t1", {}))
    journal.close()

    assert "prev_id" not in first, "первый конверт файла цепочку не несёт"
    assert second["prev_id"] == first["id"], "второй конверт несёт id первого"
    assert path.read_text(encoding="utf-8").count("\n") == 2


def test_verify_fresh_file_has_zero_gaps(tmp_path: Path) -> None:
    from blood.journal import verify

    path = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.attach(path)
    for index in range(3):
        journal.append(make("plan", "brainstem", "self", "t1", {"index": index}))
    journal.close()

    report = verify(path)
    assert report["events"] == 3
    assert report["gaps"] == []
    assert report["skipped"] == 0
    assert report["chained"] is True


def test_verify_detects_removed_event(tmp_path: Path) -> None:
    from blood.journal import verify

    path = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.attach(path)
    for index in range(4):
        journal.append(make("plan", "brainstem", "self", "t1", {"index": index}))
    journal.close()

    lines = path.read_text(encoding="utf-8").splitlines()
    del lines[1]  # удалён второй конверт — append-only нарушен
    tampered = tmp_path / "tampered.jsonl"
    tampered.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = verify(tampered)
    assert len(report["gaps"]) >= 1, "разрыв после удаления обязан быть пойман"
    assert report["events"] == 3


def test_verify_detects_substituted_id(tmp_path: Path) -> None:
    from blood.journal import verify

    path = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.attach(path)
    for index in range(3):
        journal.append(make("plan", "brainstem", "self", "t1", {"index": index}))
    journal.close()

    lines = path.read_text(encoding="utf-8").splitlines()
    forged = json.loads(lines[0])
    forged["id"] = "00000000-0000-4000-8000-000000000000"  # подмена id первого
    lines[0] = json.dumps(forged, ensure_ascii=False)
    tampered = tmp_path / "tampered.jsonl"
    tampered.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = verify(tampered)
    assert len(report["gaps"]) >= 1, "подменённый id обязан разорвать цепочку"


def test_verify_detects_inserted_event(tmp_path: Path) -> None:
    from blood.journal import verify

    path = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.attach(path)
    for index in range(3):
        journal.append(make("plan", "brainstem", "self", "t1", {"index": index}))
    journal.close()

    lines = path.read_text(encoding="utf-8").splitlines()
    outsider = make("plan", "brainstem", "self", "t1", {"index": 1.5})
    lines.insert(2, json.dumps(outsider, ensure_ascii=False))  # вставка без prev_id
    tampered = tmp_path / "tampered.jsonl"
    tampered.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = verify(tampered)
    reasons = [gap["reason"] for gap in report["gaps"]]
    assert any("без prev_id" in reason for reason in reasons), (
        "вставленный в цепочку конверт без prev_id обязан быть пойман"
    )


def test_verify_old_blood_without_chain_is_valid(tmp_path: Path) -> None:
    """Пролитая кровь v0.4.0 (без prev_id) валидна навсегда: chained=false, 0 гэпов."""
    from blood.journal import verify

    path = tmp_path / "old.jsonl"
    _write_envelopes(
        path,
        [make("act", "brainstem", "self", "t1", {}, Cost()) for _ in range(3)],
    )

    report = verify(path)
    assert report["events"] == 3
    assert report["gaps"] == []
    assert report["chained"] is False


def test_attach_continues_chain_across_sessions(tmp_path: Path) -> None:
    """Повторная сессия того же дня продолжает цепочку с последнего конверта файла."""
    from blood.journal import verify

    path = tmp_path / "blood.jsonl"
    morning = Journal()
    morning.attach(path)
    last_morning = None
    for index in range(2):
        last_morning = morning.append(make("plan", "brainstem", "self", "t-morning", {"index": index}))
    morning.close()

    evening = Journal()
    evening.attach(path)
    first_evening = evening.append(make("plan", "brainstem", "self", "t-evening", {"index": 0}))
    evening.close()

    assert first_evening["prev_id"] == last_morning["id"], (
        "цепочка продолжается с последнего конверта файла, а не с чистого листа"
    )
    report = verify(path)
    assert report["gaps"] == []
    assert report["events"] == 3


def test_attach_to_old_file_claims_chain_from_first_new_event(tmp_path: Path) -> None:
    """Старый файл без цепочки + новая сессия: цепочка заявляется с нового конверта."""
    from blood.journal import verify

    path = tmp_path / "blood.jsonl"
    _write_envelopes(
        path,
        [make("act", "brainstem", "self", "t-old", {}, Cost()) for _ in range(2)],
    )
    old_last_id = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])["id"]

    fresh = Journal()
    fresh.attach(path)
    first_new = fresh.append(make("act", "brainstem", "self", "t-new", {}, Cost()))
    fresh.close()

    assert first_new["prev_id"] == old_last_id
    report = verify(path)
    assert report["gaps"] == []
    assert report["chained"] is True


def test_verify_anchors_chain_on_last_valid_event_after_garbage(tmp_path: Path) -> None:
    """Битая строка и конверт без id якорем цепочки не служат — честный skipped."""
    from blood.journal import verify

    path = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.attach(path)
    first = journal.append(make("plan", "brainstem", "self", "t1", {"index": 0}))
    journal.close()

    # дожимаем мусор в файл (умерший процесс, чужая запись) и продолжаем сессию
    with path.open("a", encoding="utf-8") as fh:
        fh.write("не-json-мусор\n")
        fh.write(json.dumps({"ts": "2026-11-02T00:00:00Z"}) + "\n")  # конверт без id
    second_journal = Journal()
    second_journal.attach(path)
    second = second_journal.append(make("plan", "brainstem", "self", "t1", {"index": 1}))
    second_journal.close()

    assert second["prev_id"] == first["id"], "якорь — последний валидный конверт, не мусор"
    report = verify(path)
    assert report["gaps"] == []
    assert report["skipped"] == 2
    assert report["events"] == 2


def test_verify_empty_and_single_event(tmp_path: Path) -> None:
    from blood.journal import verify

    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    report = verify(empty)
    assert report == {
        "events": 0,
        "gaps": [],
        "skipped": 0,
        "chained": False,
        "content_gaps": [],
        "hashed": False,
    }, "пустой файл: ни цепочек, ни печатей, ни претензий (отчёт п.7 + п.15)"

    single = tmp_path / "single.jsonl"
    _write_envelopes(single, [make("act", "brainstem", "self", "t1", {}, Cost())])
    report = verify(single)
    assert report["events"] == 1
    assert report["gaps"] == []
    assert report["chained"] is False


def test_from_jsonl_equivalent(tmp_path: Path) -> None:
    path = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.attach(path)
    trace = new_trace_id()
    for event_type in ("plan", "act", "observe", "reflect"):
        journal.append(make(event_type, "brainstem", "self", trace, {}, Cost(tokens_in=1)))
    journal.append(make("halt", "brainstem", "self", trace, {}))
    journal.close()
    with path.open("a", encoding="utf-8") as fh:
        fh.write("мусор\n")

    restored = Journal.from_jsonl(path)
    assert [e["id"] for e in restored.all()] == [e["id"] for e in journal.all()]
    assert restored.totals(trace).tokens_in == journal.totals(trace).tokens_in
    assert restored.skipped == 1
    assert restored.by_type("halt"), "halt восстановлен"


# --- п.8: реконструкция сессии -------------------------------------------------


def test_reconstruct_completed_session(tmp_path: Path, manifest_path: Path) -> None:
    from blood.resume import reconstruct
    from synapse.gateway import Gateway

    path = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.attach(path)
    gateway = Gateway(manifest_path, journal)
    from brainstem import Loop

    loop = Loop(gateway, journal)
    plan = [
        step("sense-a", "echo", {"n": 1}, intent="первое намерение"),
        step("sense-a", "echo", {"n": 2}, intent="второе намерение"),
    ]
    assert loop.run(plan) is True
    trace_id = journal.by_type("plan")[0]["trace_id"]
    journal.close()

    session = reconstruct(path, trace_id)
    assert session["trace_id"] == trace_id
    assert session["complete"] is True
    assert session["gaps"] == []
    assert [entry["intent"] for entry in session["plan"]] == ["первое намерение", "второе намерение"]
    assert [entry["index"] for entry in session["plan"]] == [0, 1]
    assert len(session["acts"]) == 2
    assert all(act["organ"] == "sense-a" for act in session["acts"])
    assert len(session["observes"]) == 2
    assert len(session["reflects"]) == 2
    assert all(entry["satisfied"] is True for entry in session["reflects"])
    assert session["halts"] == []
    assert session["totals"]["tokens_in"] == journal.totals(trace_id).tokens_in
    assert session["totals"]["tokens_out"] == journal.totals(trace_id).tokens_out


def test_reconstruct_halted_session(tmp_path: Path, manifest_path: Path) -> None:
    from blood.resume import reconstruct
    from brainstem import Loop
    from synapse.gateway import Gateway

    path = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.attach(path)
    gateway = Gateway(manifest_path, journal)
    loop = Loop(gateway, journal)
    plan = [
        step("sense-a", "echo", {"data": "первый"}, intent="успеть до исчерпания"),
        step("sense-a", "echo", {"data": "второй"}, intent="уже не случится"),
    ]
    # FakeEcho: tokens_in = len(str(payload)) > 0 — бюджет в 1 токен исчерпан
    # первым же оплаченным вызовом: второй шаг упирается в halt (детерминированно,
    # независимо от длины payload).
    assert loop.run(plan, budget=Budget(tokens_in=1)) is False
    trace_id = journal.by_type("plan")[0]["trace_id"]
    journal.close()

    session = reconstruct(path, trace_id)
    assert session["complete"] is True, "halt — трейс закрыт по-записанному"
    assert session["gaps"] == []
    assert len(session["plan"]) == 1, "halt выпал до PLAN второго шага"
    assert len(session["acts"]) == 1
    assert len(session["halts"]) == 1
    assert "бюджет исчерпан" in session["halts"][0]["reason"]
    # W-0029 (SPEC-0001 G3 v0.4.0): бюджет проверяется и ПОСЛЕ шага — бюджет
    # исчерпан первым же вызовом, halt падает сразу после него (at_step=0);
    # второй шаг даже не планируется (раньше halt ждал проверки перед шагом 2).
    assert session["halts"][0]["at_step"] == 0
    assert session["totals"]["tokens_in"] == journal.totals(trace_id).tokens_in


def test_reconstruct_unknown_trace_is_empty(tmp_path: Path) -> None:
    from blood.resume import reconstruct

    path = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.attach(path)
    journal.append(make("plan", "brainstem", "self", "t-real", {}))
    journal.close()

    session = reconstruct(path, "нет-такого-трейса")
    assert session["events"] == 0
    assert session["complete"] is False
    assert session["plan"] == []
    assert session["acts"] == []
    # волна №24 (W-0025): reconstruction totals честны и по вниманию
    assert session["totals"] == {"tokens_in": 0, "tokens_out": 0, "seconds": 0.0, "attention": 0}


def test_reconstruct_gap_marks_incomplete(tmp_path: Path, manifest_path: Path) -> None:
    from blood.resume import reconstruct
    from brainstem import Loop
    from synapse.gateway import Gateway

    path = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.attach(path)
    gateway = Gateway(manifest_path, journal)
    loop = Loop(gateway, journal)
    assert loop.run([step("sense-a", "echo", {"n": 1}, intent="живой трейс")]) is True
    trace_id = journal.by_type("plan")[0]["trace_id"]
    journal.close()

    lines = path.read_text(encoding="utf-8").splitlines()
    forged = json.loads(lines[1])
    forged["prev_id"] = "11111111-1111-4111-8111-111111111111"  # подмена звена цепочки
    lines[1] = json.dumps(forged, ensure_ascii=False)
    tampered = tmp_path / "tampered.jsonl"
    tampered.write_text("\n".join(lines) + "\n", encoding="utf-8")

    session = reconstruct(tampered, trace_id)
    assert session["gaps"], "гэп в трейсе обязан дойти до реконструкции"
    assert session["complete"] is False
    assert session["plan"], "но сама ткань трейса реконструируется из того, что есть"
