# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмки волны №26 — оценка пути (W-0020, Ф-2.7) и нюх крови (Ф-2.3).

W-0020 (зерно PRM коллеги, Ф-2.7 ТЗ ревизора): конверт уже несёт цену события,
но оценка ПУТИ живёт только в исходе (reflect/halt). Путь, переживший отказ и
восстановленный, стоит иначе, чем гладкий — и это обязано быть названо, а не
спрятано за «run() = True». Проекция read-only `blood/path.py`: шаги, переигрки,
провалы, вопросы Человеку, компенсации, исход — и честное «восстановлен» вместо
молчаливой удачи. Без хваления (дух W-0021): факты, не «балл качества».

Ф-2.3 (нюх крови): выжимка (п.13) называет запахи окна недели; нюх — по файлу:
дубликаты id, гэпы цепочки, битые строки, события без цены/трейса, планы без
причинно-связанного исполнения, открытые трейсы, задержка наблюдения. Только
измеримое, только чтение.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from blood.envelope import Cost, make
from blood.journal import Journal
from blood.olfactory import smell, smell_all
from blood.path import path_of, render

TRACE = "wave26-test"


def _journal(tmp_path: Path) -> Journal:
    j = Journal()
    j.attach(tmp_path / "blood.jsonl")
    return j


def _plan(j: Journal, trace: str, what: str = "сделать") -> dict:
    return j.append(make("plan", "brainstem", "echo-a", trace, {"what": what}, Cost()))


def _act(j: Journal, trace: str, causation: str | None = None) -> dict:
    kw = {"causation_id": causation} if causation else {}
    return j.append(make("act", "brainstem", "echo-a", trace, {"what": "акт"}, Cost(), **kw))


def _reflect(j: Journal, trace: str) -> dict:
    return j.append(make("reflect", "brainstem", "echo-a", trace, {"verdict": "готово"}, Cost()))


def _halt(j: Journal, trace: str) -> dict:
    return j.append(make("halt", "brainstem", "echo-a", trace, {"reason": "конец"}, Cost()))


def _error(j: Journal, trace: str) -> dict:
    return j.append(make("error", "brainstem", "echo-a", trace, {"reason": "упало"}, Cost()))


def _events(j: Journal) -> list[dict]:
    return list(j.by_trace(TRACE))


# --- W-0020: оценка пути ---


def test_smooth_path_is_named_smooth(tmp_path: Path) -> None:
    j = _journal(tmp_path)
    _plan(j, TRACE)
    _act(j, TRACE, causation=_plan(j, TRACE)["id"])
    _reflect(j, TRACE)
    p = path_of(_events(j))
    assert p["outcome"] == "reflect"
    assert p["failures"] == 0 and p["retries"] == 0
    assert p["smooth"] is True and p["recovered"] is False


def test_path_counts_retry_after_failure(tmp_path: Path) -> None:
    j = _journal(tmp_path)
    plan = _plan(j, TRACE)
    _error(j, TRACE)
    _act(j, TRACE, causation=plan["id"])
    _reflect(j, TRACE)
    p = path_of(_events(j))
    assert p["failures"] == 1
    assert p["retries"] == 1, "акт после провала — переигрка, и она обязана быть названа"
    assert p["recovered"] is True and p["smooth"] is False


def test_halted_path_is_not_recovered(tmp_path: Path) -> None:
    j = _journal(tmp_path)
    _plan(j, TRACE)
    _error(j, TRACE)
    _halt(j, TRACE)
    p = path_of(_events(j))
    assert p["outcome"] == "halt"
    assert p["recovered"] is False, "провал без восстановления не приукрашается"


def test_path_counts_human_interruptions(tmp_path: Path) -> None:
    j = _journal(tmp_path)
    _plan(j, TRACE)
    j.append(make("approval.request", "brainstem", "echo-a", TRACE, {"what": "необратимое"}, Cost(attention=1)))
    _reflect(j, TRACE)
    p = path_of(_events(j))
    assert p["interruptions"] == 1


def test_path_counts_compensation_plans(tmp_path: Path) -> None:
    j = Journal()
    j.attach(tmp_path / "c.jsonl")
    plan = _plan(j, TRACE)
    act = _act(j, TRACE, causation=plan["id"])
    comp_trace = "comp-1"
    j.append(make("plan", "brainstem", "echo-a", comp_trace, {"what": "компенсация акта", "act_id": act["id"]}, Cost(), causation_id=act["id"]))
    j.append(make("reflect", "brainstem", "echo-a", comp_trace, {"verdict": "отменено"}, Cost()))
    p = path_of(list(j.by_trace(comp_trace)))
    assert p["compensations"] == 1


def test_render_never_praises(tmp_path: Path) -> None:
    j = _journal(tmp_path)
    plan = _plan(j, TRACE)
    _error(j, TRACE)
    _act(j, TRACE, causation=plan["id"])
    _reflect(j, TRACE)
    text = render(path_of(_events(j)))
    assert "успешно" not in text.lower(), "рендер пути не хвалит (дух W-0021)"
    assert "1" in text and "провал" in text.lower()
    assert "восстановлен" in text.lower()


def test_open_trace_is_named_open(tmp_path: Path) -> None:
    j = _journal(tmp_path)
    _plan(j, TRACE)
    p = path_of(_events(j))
    assert p["outcome"] == "open", "открытый трейс назван открытым, не приукрашен"


def test_path_over_all_live_blood_of_the_house() -> None:
    """Живая кровь дома: путь считается по каждому трейсу каждого файла — без ошибок."""
    root = Path(__file__).resolve().parent.parent
    files = sorted((root / "runs").glob("**/blood.jsonl"))
    assert len(files) >= 20, "кровь дома обязана быть в зоне (файлов мало — зона сузилась)"
    outcomes = {"reflect", "halt", "open"}
    seen = 0
    for path in files:
        from blood.journal import verify

        events = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        traces: dict[str, list[dict]] = {}
        for e in events:
            if isinstance(e, dict) and e.get("trace_id"):
                traces.setdefault(e["trace_id"], []).append(e)
        for trace_id, evs in traces.items():
            p = path_of(evs)
            assert p["outcome"] in outcomes, (path, trace_id, p)
            seen += 1
    assert seen >= 100, "трейсов в живой крови дома ожидаемо много"


# --- Ф-2.3: нюх крови ---


def test_smell_catches_duplicate_id(tmp_path: Path) -> None:
    path = tmp_path / "blood.jsonl"
    j = _journal(tmp_path)
    e = _plan(j, TRACE)
    lines = path.read_text(encoding="utf-8").splitlines()
    # второй конверт с чужим id — подделка; для честного прогона строим файл руками
    forged = dict(e)
    lines.append(json.dumps(forged, ensure_ascii=False))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    smells = smell(path)
    assert any("дубликат" in s for s in smells), smells


def test_smell_catches_bad_line(tmp_path: Path) -> None:
    path = tmp_path / "blood.jsonl"
    j = _journal(tmp_path)
    _plan(j, TRACE)
    with path.open("a", encoding="utf-8") as fh:
        fh.write("::: битая строка :::\n")
    smells = smell(path)
    assert any("битых строк" in s for s in smells), smells


def test_smell_catches_missing_cost(tmp_path: Path) -> None:
    path = tmp_path / "blood.jsonl"
    j = _journal(tmp_path)
    _plan(j, TRACE)
    lines = path.read_text(encoding="utf-8").splitlines()
    e = json.loads(lines[0])
    del e["cost"]
    path.write_text(json.dumps(e, ensure_ascii=False) + "\n", encoding="utf-8")
    smells = smell(path)
    assert any("без цены" in s for s in smells), smells


def test_smell_catches_event_without_trace(tmp_path: Path) -> None:
    path = tmp_path / "blood.jsonl"
    j = _journal(tmp_path)
    _plan(j, TRACE)
    lines = path.read_text(encoding="utf-8").splitlines()
    e = json.loads(lines[0])
    del e["trace_id"]
    path.write_text(json.dumps(e, ensure_ascii=False) + "\n", encoding="utf-8")
    smells = smell(path)
    assert any("без trace_id" in s for s in smells), smells


def test_smell_catches_plan_without_linked_act(tmp_path: Path) -> None:
    path = tmp_path / "blood.jsonl"
    j = _journal(tmp_path)
    _plan(j, TRACE)
    _reflect(j, TRACE)
    smells = smell(path)
    assert any("план" in s and "без" in s for s in smells), smells


def test_smell_is_read_only(tmp_path: Path) -> None:
    path = tmp_path / "blood.jsonl"
    j = _journal(tmp_path)
    _plan(j, TRACE)
    _reflect(j, TRACE)
    before = path.read_bytes()
    smell(path)
    assert path.read_bytes() == before, "нюх только читает: байты крови не меняются"


def test_smell_all_covers_live_house() -> None:
    """Живой свип по всему дому: каждый файл пролитой крови понюхан, запахи названы."""
    root = Path(__file__).resolve().parent.parent
    report = smell_all(root)
    files = sorted((root / "runs").glob("**/blood.jsonl"))
    assert len(report) >= len(files) - 1, "нюх обязан смотреть на всю пролитую кровь дома"
    for rel, smells in report.items():
        assert isinstance(smells, list) and all(isinstance(s, str) for s in smells), rel
