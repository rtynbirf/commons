"""Приёмки-стык такта 2 волны №18: третье измерение дневника — на их живом коде.

Стык-дисциплина волны №15: параллельная реализация дневника выметена, их
`blood/diary.py` (0.37.0) принят базой; этот сюит гоняет МОИ измерения честности
(двенадцать граней волны №18) по их публичному API (`entries`/`render`/`to_jsonl`)
— контрольный забег третьим путём, как 0.35.1 гонял Ф-0 на их коде. Кровь —
истина: дневник ничего не пишет в неё.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from blood.envelope import Cost, make
from blood.journal import Journal

REPO_ROOT = Path(__file__).resolve().parents[1]


def _journal(tmp_path: Path, trace: str = "j1") -> tuple[Path, Journal]:
    journal = Journal()
    journal.attach(tmp_path / "blood.jsonl")
    return tmp_path / "blood.jsonl", journal


def test_junction_plan_is_not_fact(tmp_path: Path) -> None:
    """A05: план без причинного действия — «что не сделано»; causation_id подтверждает."""
    from blood.diary import entries

    path, journal = _journal(tmp_path)
    plan = journal.append(make("plan", "brainstem", "self", "j1", {"act": "прочитать отчёт", "task": "прочитать отчёт"}))
    journal.append(make("plan", "brainstem", "self", "j1", {"act": "сходить в сеть", "task": "сходить в сеть"}))
    journal.append(make("act", "brainstem", "self", "j1", {"act": "прочитан отчёт"}, cost=Cost(1, 2, 0.3), causation_id=plan["id"]))
    journal.close()

    book = entries(path)
    undone = [r for r in book["records"] if "что не сделано" in r]
    assert len(undone) == 1, "только план без причинного действия — не сделан"
    assert "сходить в сеть" in undone[0]["что"], "незакрытый план назван"
    assert undone[0]["что не сделано"].startswith("исполнение не подтверждено"), "человеческая причина"


def test_junction_no_success_word_ever(tmp_path: Path) -> None:
    """Слово «успешно» не встречается вовсе — доверие называется по классу п.10."""
    from blood.diary import render

    path, journal = _journal(tmp_path)
    journal.append(make("act", "brainstem", "self", "j1", {"act": "дело"}, trust="verified"))
    journal.append(make("act", "brainstem", "self", "j1", {"act": "весть"}, trust="unverified"))
    journal.append(make("act", "brainstem", "self", "j1", {"act": "прочее"}))
    journal.close()

    text = render(path)
    assert "успешно" not in text.lower(), "слово-обещание запрещено дневнику"
    assert "проверено" in text, "verified назван по-человечески"
    assert "независимых проверок не было" in text, "unverified назван честно"
    assert "доверие не заявлено" in text, "unknown назван честно"


def test_junction_honest_unknown_time(tmp_path: Path) -> None:
    """A02: occurred_at=null — «неизвестно», фиктивная дата не подставляется."""
    from blood.diary import entries

    path, journal = _journal(tmp_path)
    journal.append(make("act", "brainstem", "self", "j1", {"act": "дело"}, occurred_at=None))
    journal.close()

    record = entries(path)["records"][0]
    assert "неизвестно" in record["когда"].lower(), "честное незнание времени"


def test_junction_undo_not_promised(tmp_path: Path) -> None:
    """W-0024: компенсатора нет — дневник отмены не обещает."""
    from blood.diary import render

    path, journal = _journal(tmp_path)
    journal.append(make("act", "brainstem", "self", "j1", {"act": "дело"}))
    journal.close()

    text = render(path)
    assert "не обещается" in text.lower() or "не обещает" in text.lower(), "отмена не обещается"
    assert "W-0024" in text, "причина названа"


def test_junction_refusals_named(tmp_path: Path) -> None:
    """W-0021: отказ — данные, а не стыд: veto/halt/error названы словами."""
    from blood.diary import render

    path, journal = _journal(tmp_path)
    journal.append(make("veto", "brainstem", "self", "j1", {"what": "запрос наружу", "reason": "сеть не заявлена"}))
    journal.append(make("halt", "brainstem", "self", "j1", {"reason": "бюджет исчерпан"}))
    journal.append(make("error", "brainstem", "self", "j1", {"error": "файл недоступен"}))
    journal.close()

    text = render(path)
    assert "«нет»" in text, "veto назван отказом"
    assert "остановлено" in text, "halt назван остановкой"
    assert "ошибка" in text, "error назван ошибкой"


def test_junction_gap_and_broken_lines_named(tmp_path: Path) -> None:
    """Гэп цепочки красит дневник, битые строки посчитаны честно."""
    from blood.diary import entries, render

    path, journal = _journal(tmp_path)
    journal.append(make("plan", "brainstem", "self", "j1", {"act": "дело"}))
    journal.append(make("act", "brainstem", "self", "j1", {"act": "дело сделано"}))
    journal.close()
    lines = path.read_text(encoding="utf-8").splitlines()
    # Настоящий разрыв: план вынут из файла — акт остался с prev_id на вынутого;
    # битая строка в голове (битая строка цепочку НЕ рвёт — находка зелёного прогона).
    path.write_text("\n".join(["{битая", lines[1]]) + "\n", encoding="utf-8")

    book = entries(path)
    assert book["damaged"], "разрыв цепочки — damaged"
    assert book["broken_lines"] == 1, "битая строка посчитана"
    assert "ЖУРНАЛ ПОВРЕЖДЁН" in render(path), "повреждение названо человеку словами"


def test_junction_totals_sum_costs(tmp_path: Path) -> None:
    """Полная цена трейса — сумма цен конвертов."""
    from blood.diary import entries

    path, journal = _journal(tmp_path)
    journal.append(make("act", "brainstem", "self", "j1", {"act": "а"}, cost=Cost(10, 20, 1.5)))
    journal.append(make("act", "brainstem", "self", "j1", {"act": "б"}, cost=Cost(1, 2, 0.5)))
    journal.close()

    totals = entries(path)["totals"]
    assert totals == {"tokens_in": 11, "tokens_out": 22, "seconds": 2.0}, "цена сходится"


def test_junction_empty_journal_is_honest(tmp_path: Path) -> None:
    """Пустая кровь — честное «сказать нечего», не выдумка."""
    from blood.diary import render

    path, journal = _journal(tmp_path)
    journal.close()
    assert "Записей нет" in render(path), "пустота названа честно"


def test_junction_trace_filter_excludes_others(tmp_path: Path) -> None:
    """A03: фильтр трейса не пускает чужих событий в запись."""
    from blood.diary import entries

    path, journal = _journal(tmp_path)
    journal.append(make("act", "brainstem", "self", "j1", {"act": "моё"}))
    journal.append(make("act", "brainstem", "self", "j2", {"act": "чужое"}))
    journal.close()

    book = entries(path, "j1")
    whats = [r["что"] for r in book["records"]]
    assert any("моё" in w for w in whats) and not any("чужое" in w for w in whats), "чужое не в записи"


def test_junction_diary_never_writes_blood(tmp_path: Path) -> None:
    """Read-проекция: кровь после entries/render/to_jsonl — байт в байт та же."""
    from blood.diary import render, to_jsonl

    path, journal = _journal(tmp_path)
    journal.append(make("act", "brainstem", "self", "j1", {"act": "дело"}))
    journal.close()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    render(path)
    to_jsonl(path, tmp_path / "diary.jsonl")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before, "дневник не переписывает кровь"


def test_junction_jsonl_export_one_line_per_trace(tmp_path: Path) -> None:
    """Такт 2: JSONL-экспорт — одна строка на трейс, те же факты, что у человека."""
    from blood.diary import to_jsonl

    path, journal = _journal(tmp_path)
    journal.append(make("act", "brainstem", "self", "j1", {"act": "дело"}))
    journal.append(make("act", "brainstem", "self", "j2", {"act": "другое дело"}))
    journal.close()

    out = to_jsonl(path, tmp_path / "diary.jsonl")
    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 2, "одна строка — один трейс"
    for row in rows:
        assert {"trace_id", "records", "totals"} <= set(row), "машина читает те же записи"
    assert any(r["trace_id"] == "j1" for r in rows) and any(r["trace_id"] == "j2" for r in rows)


def test_junction_reads_all_house_blood() -> None:
    """Контрольный забег по живой крови дома: старый стиль (волна №17), адаптерная кровь (их такт 2)."""
    from blood.diary import entries, render

    for rel in ("runs/2026-11-03-wave17-origin/blood.jsonl", "runs/2026-11-03-wave17-membrane-blood/blood.jsonl"):
        path = REPO_ROOT / rel
        book = entries(path)
        assert book["damaged"] == [], f"{rel}: 0 гэпов"
        text = render(path)
        assert "успешно" not in text.lower(), f"{rel}: слово-обещание протекло"
        assert "Записей нет" not in text, f"{rel}: кровь есть, записей быть должно"
