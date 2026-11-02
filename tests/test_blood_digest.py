"""Выжимка крови — недельный агрегат — W-0019, SPEC-0003 п.13 (волна №19).

Зерно «сна и консолидации» коллеги: дом сам выжимает смысл из крови —
что понял, что болело, что закрыл, чем пахнет — текстом для Человека.
Приёмки честности агрегата: окно по записи (вне окна — названо, не спрятано),
отказы считаются провалами (W-0021), открытые трейсы названы, запахи —
только измеримые сигналы, кровь read-only (выжимка не переписывает).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from blood.digest import render_digest, week_digest
from blood.envelope import Cost, make
from blood.journal import Journal

NOW = datetime(2026, 11, 3, 12, 0, 0, tzinfo=timezone.utc)
FRESH = "2026-11-03T10:00:00Z"   # в окне (NOW − 7 дней = 27.10)
OLD = "2026-10-20T10:00:00Z"     # вне окна
TRACE = "digest-t"


def _envelope(kind: str, ts: str, payload: dict | None = None, **kwargs) -> dict:
    env = make(kind, "brainstem", "self", TRACE, payload or {}, Cost(1, 1, 0.5), **kwargs)
    env["ts"] = ts  # детерминированное окно для приёмок (схема валидирует формат)
    return env


def _pour(path: Path, envelopes: list[dict]) -> Path:
    path.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in envelopes) + "\n",
        encoding="utf-8",
    )
    return path


def _week_file(tmp_path: Path) -> Path:
    journal = Journal()
    journal.attach(tmp_path / "blood.jsonl")
    journal.append(make("plan", "brainstem", "self", "t-open", {"act": "не доведён"}, Cost()))  # без act-связи — незакрытый и неисполненный
    journal.append(make("act", "brainstem", "self", "t-done", {"act": "сделал дело"}, Cost(3, 2, 1.0)))
    journal.append(make("veto", "brainstem", "self", "t-veto", {"reason": "рано"}, Cost()))
    journal.append(make("reflect", "brainstem", "self", "t-done", {"verdict": "дело сделано, проверено"}, Cost()))
    journal.close()
    events = Journal.from_jsonl(tmp_path / "blood.jsonl").all()
    return _pour(tmp_path / "blood.jsonl", [
        dict(e, ts=FRESH) for e in events
    ])


# --- окно недели: в окне считается, вне окна названо ------------------------------


def test_window_counts_only_fresh_but_names_the_old(tmp_path: Path) -> None:
    path = _pour(tmp_path / "blood.jsonl", [
        _envelope("act", FRESH),
        _envelope("act", OLD),
    ])
    d = week_digest([path], now=NOW)
    assert d["events"] == 1
    assert d["outside_window"] == 1  # не забыто — названо счётчиком
    text = render_digest([path], now=NOW)
    assert "вне окна" in text


def test_refusals_are_counted_as_pain(tmp_path: Path) -> None:
    path = _week_file(tmp_path)
    d = week_digest([path], now=NOW)
    assert d["ached"]["refusals"] == {"veto": 1}
    assert d["ached"]["refusals_total"] == 1
    assert "сказано «нет»" not in d and "veto: 1" in render_digest([path], now=NOW)


def test_open_trace_is_named_not_adorned(tmp_path: Path) -> None:
    """Трейс без закрытия (последний конверт не halt/reflect) назван открытым."""
    path = _week_file(tmp_path)
    d = week_digest([path], now=NOW)
    assert d["closed"]["closed"] == 1  # t-done закрыт reflect'ом
    assert "t-open" in d["closed"]["open"]
    assert "без закрытия" in render_digest([path], now=NOW)


def test_verdicts_are_human_text(tmp_path: Path) -> None:
    path = _week_file(tmp_path)
    d = week_digest([path], now=NOW)
    assert "дело сделано, проверено" in d["understood"]["verdicts"]


# --- чем пахнет: только измеримые сигналы ------------------------------------------


def test_smells_name_unknown_fact_time_and_unfulfilled_plan(tmp_path: Path) -> None:
    """Незаявленное время факта и план без причинной связи — измеримые запахи."""
    path = _week_file(tmp_path)
    text = render_digest([path], now=NOW)
    assert "время факта не заявлено" in text  # их семантика: make не штампует occurred_at
    assert "планов без причинно-связанного исполнения: 1" in text


def test_smell_max_observation_delay(tmp_path: Path) -> None:
    env = _envelope("act", FRESH, occurred_at="2026-11-02T10:00:00Z")
    path = _pour(tmp_path / "blood.jsonl", [env])
    text = render_digest([path], now=NOW)
    assert "задержка наблюдения" in text
    assert "1 day" in text  # факт 02.11 10:00 → запись 03.11 10:00


def test_damage_stains_the_digest(tmp_path: Path) -> None:
    """Гэп цепочки — боль, не запах: файл назван повреждённым."""
    journal = Journal()
    journal.attach(tmp_path / "blood.jsonl")
    journal.append(make("act", "brainstem", "self", TRACE, {}, Cost()))
    journal.close()
    good = Journal.from_jsonl(tmp_path / "blood.jsonl").all()
    forged = [dict(good[0])]
    middle = dict(good[0])
    middle["id"] = str(__import__("uuid").uuid4())
    middle["prev_id"] = str(__import__("uuid").uuid4())  # разрыв
    forged.append(middle)
    path = _pour(tmp_path / "blood.jsonl", forged)
    d = week_digest([path], now=NOW)
    assert d["ached"]["damaged_files"]
    assert "ЖУРНАЛЫ ПОВРЕЖДЕНЫ" in render_digest([path], now=NOW)


# --- цена и честность пустого окна ---------------------------------------------------


def test_price_sums_the_window(tmp_path: Path) -> None:
    path = _week_file(tmp_path)
    d = week_digest([path], now=NOW)
    assert d["price"]["tokens_in"] == 3  # только act несёт токены (plan/veto/reflect — нулевые)
    assert d["price"]["seconds"] == 1.0


def test_empty_window_is_honest(tmp_path: Path) -> None:
    path = _pour(tmp_path / "blood.jsonl", [_envelope("act", OLD)])
    text = render_digest([path], now=NOW)
    assert "За окно крови не попало" in text
    assert "вне окна" in text


def test_missing_file_is_skipped_honestly(tmp_path: Path) -> None:
    d = week_digest([tmp_path / "нет-такого-файла.jsonl"], now=NOW)
    assert d["files_scanned"] == 0
    assert d["events"] == 0


# --- read-only: выжимка не переписывает кровь ----------------------------------------


def test_digest_is_read_only(tmp_path: Path) -> None:
    path = _week_file(tmp_path)
    before = path.read_bytes()
    render_digest([path], now=NOW)
    assert path.read_bytes() == before  # проекция не пишет в кровь
