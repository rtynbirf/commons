"""Дневник человека — read-проекция крови — W-0023, SPEC-0003 п.12 (волна №18).

Приёмки матрицы пакета «Human Membrane»: A04 (дневник понятен независимому
читателю — действие и результат словами) и A05 (план не показан как
исполнение — грех №2467 в приложении к журналу). Плюс честные правила дома:
«успешно» без проверяемого результата не пишется, неизвестное время остаётся
неизвестным (A02), отказ назван отказом (W-0021), отмена не обещается
(W-0024), битые строки и гэпы цепочки красятся в шапке.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from blood.diary import entries, render
from blood.envelope import Cost, make
from blood.journal import Journal

TRACE = "diary-t"


def _pour(path: Path, envelopes: list[dict]) -> Path:
    path.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in envelopes) + "\n",
        encoding="utf-8",
    )
    return path


def _session(path: Path) -> list[dict]:
    journal = Journal()
    journal.attach(path)
    plan = journal.append(make(
        "plan", "brainstem", "self", TRACE, {"act": "собрать отчёт"}, Cost(1, 2, 0.5),
    ))
    act = journal.append(make(
        "act", "brainstem", "self", TRACE, {"act": "собрать отчёт"},
        Cost(10, 5, 1.5), causation_id=plan["id"],
    ))
    journal.append(make(
        "veto", "brainstem", "self", TRACE, {"reason": "публиковать рано"}, Cost(0, 0, 0.1),
    ))
    journal.close()
    return [plan, act, journal.all()[-1]]


# --- A05: план не показан как исполнение ---------------------------------------


def test_plan_is_not_shown_as_execution(tmp_path: Path) -> None:
    path = _pour(tmp_path / "blood.jsonl", _session(tmp_path / "src.jsonl"))
    text = render(path, TRACE)
    plan_line = next(line for line in text.splitlines() if "намерение" in line)
    assert "исполнение" not in plan_line.replace("исполнение не подтверждено", "")
    assert "намерение — не факт" in text


def test_success_is_never_written_without_verification(tmp_path: Path) -> None:
    """«Успешно» не пишется без проверяемого результата.

    Незаявленное доверие читается честно («доверие не заявлено»), явная
    заявка unverified — «проверок не было»; в обоих случаях дневник не
    называет действие успешным.
    """
    path = _pour(tmp_path / "blood.jsonl", _session(tmp_path / "src.jsonl"))
    text = render(path, TRACE)
    assert "успешно" not in text.lower()
    assert "доверие не заявлено" in text  # их семантика: make не штампует незаявленное


def test_explicit_unverified_is_named(tmp_path: Path) -> None:
    src = _session(tmp_path / "src.jsonl")
    src[1] = dict(src[1], trust="unverified")
    path = _pour(tmp_path / "blood.jsonl", src)
    text = render(path, TRACE)
    assert "успешно" not in text.lower()
    assert "независимых проверок не было" in text


def test_verified_action_says_checked(tmp_path: Path) -> None:
    src = _session(tmp_path / "src.jsonl")
    src[1] = dict(src[1], trust="verified")
    path = _pour(tmp_path / "blood.jsonl", src)
    assert "проверено" in render(path, TRACE)


# --- A04: понятен независимому читателю -----------------------------------------


def test_record_names_action_and_result(tmp_path: Path) -> None:
    path = _pour(tmp_path / "blood.jsonl", _session(tmp_path / "src.jsonl"))
    text = render(path, TRACE)
    assert "собрать отчёт" in text  # действие человеческими словами
    assert "кто инициировал" in text and "brainstem" in text
    assert "цена:" in text
    assert "можно ли отменить" in text
    assert "чем подтверждён" in text


def test_refusal_is_named_a_refusal(tmp_path: Path) -> None:
    """Отказ — данные, а не стыд (W-0021): veto назван словами."""
    path = _pour(tmp_path / "blood.jsonl", _session(tmp_path / "src.jsonl"))
    assert "сказано «нет»" in render(path, TRACE)
    assert "публиковать рано" in render(path, TRACE)


# --- честность времени и отмены ---------------------------------------------------


def test_unknown_fact_time_stays_unknown(tmp_path: Path) -> None:
    """A02 в дневнике: неизвестное время — «неизвестно», не выдумка."""
    journal = Journal()
    journal.attach(tmp_path / "blood.jsonl")
    journal.append(make(
        "act", "brainstem", "self", TRACE, {"act": "внешний факт"}, Cost(),
        occurred_at=None,
    ))
    journal.close()
    text = render(tmp_path / "blood.jsonl", TRACE)
    assert "неизвестно (увидено и записано" in text


def test_undo_is_not_promised(tmp_path: Path) -> None:
    """Отменяемость честная (W-0024, волна №22): класс не заявлен — отмена не обещается;
    незаявленное не достраивается (A02) — дневник не выдумывает отмену."""
    path = _pour(tmp_path / "blood.jsonl", _session(tmp_path / "src.jsonl"))
    text = render(path, TRACE)
    assert "класс обратимости не заявлен — отмена не обещается" in text
    assert "отменять нечего — план не исполнялся" in text


def test_unfulfilled_plan_is_named(tmp_path: Path) -> None:
    """Что НЕ сделано: план без действия с причинной связью назван честно."""
    journal = Journal()
    journal.attach(tmp_path / "blood.jsonl")
    journal.append(make(
        "plan", "brainstem", "self", TRACE, {"act": "никем не исполненный план"}, Cost(),
    ))
    journal.close()
    book = entries(tmp_path / "blood.jsonl", TRACE)
    assert book["plans_unfulfilled"] == 1
    assert "что не сделано" in book["records"][0]
    assert "исполнение не подтверждено кровью" in book["records"][0]["что не сделано"]


def test_fulfilled_plan_is_confirmed_by_causation(tmp_path: Path) -> None:
    """Исполнение подтверждается причинной связью act → plan, не порядком."""
    path = _pour(tmp_path / "blood.jsonl", _session(tmp_path / "src.jsonl"))
    book = entries(path, TRACE)
    assert book["plans_unfulfilled"] == 0
    assert "что не сделано" not in book["records"][0]


# --- целость журнала и цена -------------------------------------------------------


def test_broken_lines_are_named(tmp_path: Path) -> None:
    src = _session(tmp_path / "src.jsonl")
    path = _pour(tmp_path / "blood.jsonl", src)
    with path.open("a", encoding="utf-8") as fh:
        fh.write("{битая строка без json\n")
    text = render(path, TRACE)
    assert "Битых строк пропущено честно: 1" in text


def test_chain_gap_stains_the_diary(tmp_path: Path) -> None:
    src = _session(tmp_path / "src.jsonl")
    forged = [dict(src[0])]
    middle = dict(src[1])
    middle["prev_id"] = str(uuid.uuid4())  # разрыв: не id первого конверта
    forged.append(middle)
    path = _pour(tmp_path / "blood.jsonl", forged)
    text = render(path, TRACE)
    assert "ЖУРНАЛ ПОВРЕЖДЁН" in text


def test_trace_totals_sum_costs(tmp_path: Path) -> None:
    from pytest import approx

    path = _pour(tmp_path / "blood.jsonl", _session(tmp_path / "src.jsonl"))
    book = entries(path, TRACE)
    assert book["totals"] == {"tokens_in": 11, "tokens_out": 7, "seconds": approx(2.1)}


def test_empty_journal_is_honest(tmp_path: Path) -> None:
    path = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.attach(path)
    journal.close()
    text = render(path, TRACE)
    assert "Записей нет" in text


def test_trace_filter_excludes_others(tmp_path: Path) -> None:
    journal = Journal()
    journal.attach(tmp_path / "blood.jsonl")
    journal.append(make("act", "brainstem", "self", "other-trace", {"act": "чужой трейс"}, Cost()))
    journal.append(make("act", "brainstem", "self", TRACE, {"act": "мой трейс"}, Cost()))
    journal.close()
    book = entries(tmp_path / "blood.jsonl", TRACE)
    assert len(book["records"]) == 1
    assert "мой трейс" in book["records"][0]["что"]
