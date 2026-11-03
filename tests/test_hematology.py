"""Приёмка SPEC-0003 п.6 (v0.4.0): гематология — вся пролитая кровь валидна навсегда.

Кровь под runs/ — вещественное доказательство жизни организма; однажды записанное
не гниёт. tests/test_first_pulse.py охраняет первый пульс как подлинность прогона
(артефакты, цепь, G1); эта приёмка держит инвариант всего тела: ПЕРЕЧИТЫВАЕТ ВСЕ
журналы пролитой крови по схеме — полная цена каждого события, время не откатывается
(append-only), сессии различимы по trace_id, id событий не повторяются (спайки нет).
Спека тоже сдаёт свою кровь: пример конверта и словарь типов SPEC-0003 сверяются
со схемой — дрейф спеки и схемы невозможен.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from blood.envelope import load_schema, validate

REPO_ROOT = Path(__file__).resolve().parent.parent
JOURNALS = sorted((REPO_ROOT / "runs").glob("*/blood.jsonl"))
SPEC_0003 = REPO_ROOT / "specs" / "SPEC-0003-blood-envelope.md"

FULL_PRICE = {"tokens_in", "tokens_out", "seconds"}


def events_of(journal: Path) -> list[dict]:
    lines = journal.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


# --- вся пролитая кровь (SPEC-0003 п.6) -------------------------------------


def test_blood_exists() -> None:
    assert JOURNALS, "пролитой крови нет: организм ещё не жил"


@pytest.mark.parametrize("journal", JOURNALS, ids=lambda p: p.parent.name)
def test_journal_not_empty(journal: Path) -> None:
    assert len(events_of(journal)) > 0, f"пустой журнал крови: {journal}"


@pytest.mark.parametrize("journal", JOURNALS, ids=lambda p: p.parent.name)
def test_every_envelope_valid_by_schema(journal: Path) -> None:
    for event in events_of(journal):
        validate(event)  # EnvelopeError = кровь подделана после прогона


@pytest.mark.parametrize("journal", JOURNALS, ids=lambda p: p.parent.name)
def test_every_event_has_full_price(journal: Path) -> None:
    for event in events_of(journal):
        # Полная цена (SPEC-0003 п.3): обязательное трио в каждом конверте.
        assert FULL_PRICE <= set(event["cost"]), (
            f"{journal.name}: событие {event['id']} без полной цены (SPEC-0003 п.3)"
        )
        assert event["cost"]["tokens_in"] >= 0
        assert event["cost"]["tokens_out"] >= 0
        assert event["cost"]["seconds"] >= 0
        # Внимание Человека (SPEC-0003 п.17, W-0025, волна №23) — аддитивно:
        # отсутствие = не заявлено (A02), заявленное — целое ≥ 0; ноль не
        # пишется, поэтому встреченное внимание ≥ 1 (старый стиль жив).
        if "attention" in event["cost"]:
            assert isinstance(event["cost"]["attention"], int) and event["cost"]["attention"] >= 1, (
                f"{journal.name}: событие {event['id']} несёт внимание не по словарю (SPEC-0003 п.17)"
            )


@pytest.mark.parametrize("journal", JOURNALS, ids=lambda p: p.parent.name)
def test_time_does_not_flow_backwards(journal: Path) -> None:
    stamps = [event["ts"] for event in events_of(journal)]
    assert stamps == sorted(stamps), (
        f"{journal.name}: время откатилось — append-only нарушен (SPEC-0003 п.4)"
    )


@pytest.mark.parametrize("journal", JOURNALS, ids=lambda p: p.parent.name)
def test_sessions_are_distinguishable(journal: Path) -> None:
    events = events_of(journal)
    traces = {event["trace_id"] for event in events}
    assert traces, f"{journal.name}: ни одной сессии"
    for event in events:
        assert event["trace_id"], f"{journal.name}: событие {event['id']} без trace_id"


def test_event_ids_are_unique_across_the_body() -> None:
    ids = [event["id"] for journal in JOURNALS for event in events_of(journal)]
    assert len(ids) == len(set(ids)), "кровь сращена: один id встречается дважды"


# --- цепочка prev_id (SPEC-0003 п.7, v0.5.0) ----------------------------------


@pytest.mark.parametrize("journal", JOURNALS, ids=lambda p: p.parent.name)
def test_journal_chain_has_no_gaps(journal: Path) -> None:
    """Разрыв журнала обнаруживается при чтении: пролитая кровь без гэпов.

    Кровь без цепочки (v0.4.0 и старше) валидна навсегда — verify не заявляет
    гэпов там, где цепочка не начата; кровь с цепочкой обязана быть целой.
    """
    from blood.journal import verify

    report = verify(journal)
    assert report["gaps"] == [], (
        f"{journal.name}: разрыв цепочки prev_id — append-only нарушен: "
        f"{report['gaps'][:3]}"
    )


# --- хэш-цепочка содержания и якорная книга (SPEC-0003 п.15, W-0026, волна №21)

ANCHORS = REPO_ROOT / "blood" / "anchors.jsonl"


@pytest.mark.parametrize("journal", JOURNALS, ids=lambda p: p.parent.name)
def test_journal_content_chain_has_no_gaps(journal: Path) -> None:
    """Хэш-гигиена: заверенная кровь цела — подменённый конверт, конверт в
    заверенной зоне без печати, усечённый хвост (по якорю) — content_gaps.
    Кровь без печатей (v0.4–v0.11) валидна навсегда: hashed=False, претензий нет.
    """
    from blood.journal import verify

    report = verify(journal)
    assert report["content_gaps"] == [], (
        f"{journal.name}: хэш-цепочка содержания порвана — append-only нарушен: "
        f"{report['content_gaps'][:3]}"
    )


def test_anchor_book_is_wellformed() -> None:
    """Якорная книга (blood/anchors.jsonl) — по одной записи-печати на строку:
    файл крови, счёт событий, id и канонический хэш последнего конверта.
    Книги может не быть — печать крови начата волной №21."""
    if not ANCHORS.exists():
        return
    for lineno, raw in enumerate(ANCHORS.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        record = json.loads(raw)
        assert {"file", "events", "last_id", "last_sha256", "sealed_at"} <= set(record), (
            f"anchors.jsonl:{lineno}: запись без полей печати"
        )
        assert isinstance(record["events"], int) and record["events"] >= 0
        assert record["last_sha256"] is None or re.fullmatch(r"[0-9a-f]{64}", record["last_sha256"])


def test_journals_match_their_last_anchor() -> None:
    """Живая кровь не урезана и не подменена после печати: для каждого файла
    с якорем — событий не меньше запечатанных; при равенстве последний конверт
    совпадает с якорем (id и канонический хэш). Файл, выросший после печати,
    якорю верен — рост не гэп."""
    from blood.journal import verify

    if not ANCHORS.exists():
        return
    last_by_file: dict[str, dict] = {}
    for raw in ANCHORS.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            record = json.loads(raw)
            last_by_file[record["file"]] = record  # последняя печать — действующая
    for journal in JOURNALS:
        anchor = last_by_file.get(str(journal.relative_to(REPO_ROOT)))
        if anchor is None:
            continue
        report = verify(journal, anchor=anchor)
        assert report["content_gaps"] == [], (
            f"{journal.name}: кровь разошлась с печатью: {report['content_gaps'][:2]}"
        )


# --- спека сдаёт свою кровь (приёмка SPEC-0003, п.1 и п.3) -------------------


def test_spec_example_is_valid_blood() -> None:
    text = SPEC_0003.read_text(encoding="utf-8")
    block = re.search(r"```json\n(.*?)```", text, re.DOTALL)
    assert block, "в SPEC-0003 нет примера конверта"
    validate(json.loads(block.group(1)))


def test_spec_type_dictionary_matches_schema_enum() -> None:
    schema = load_schema()
    text = SPEC_0003.read_text(encoding="utf-8")
    section = text.split("## Типы событий", 1)[1]
    line = next(l for l in section.splitlines() if l.strip().startswith("`"))
    spec_types = set(re.findall(r"`([a-z.]+)`", line))
    schema_types = set(schema["properties"]["type"]["enum"])
    assert spec_types == schema_types, (
        f"словарь типов спеки и схемы разошёлся: "
        f"только в спеке={sorted(spec_types - schema_types)}, "
        f"только в схеме={sorted(schema_types - spec_types)}"
    )
