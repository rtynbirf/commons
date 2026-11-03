# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмки волны №21 — печать и приёмка (W-0026 + W-0027, «одно другое не исключает»).

W-0026 (SPEC-0003 п.15): кровь, заверенная от подделки — хэш-цепочка содержимого
`prev_sha256` (канонический SHA-256 предыдущего конверта файла) + внешний якорь
против усечения хвоста (`seal`/`verify(path, anchor)`). Приёмка-предписание F-01
волны №20 («цепочка шьёт порядок, а не байты») переворачивается честно: в
хэшированной крови подмена содержимого ловится при чтении. Старая кровь
(v0.4–v0.11) без хэшей валидна навсегда — граница остаётся названной.

W-0027 (SPEC-0001 v0.3.0): REFLECT по проверяемому критерию — `Step.accept`
(JSON-схема или предикат). Зеркало D2/F-06 коллег: `{"error":…, "ok": false}`
от органа больше не считается успехом, когда шаг объявил критерий. Без
критерия — прежняя рефлексия M1, аддитивно.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from blood.envelope import Cost, EnvelopeError, canonical_sha256, make, new_trace_id
from blood.journal import Journal, seal, verify
from brainstem.loop import Loop, Step
from synapse.gateway import Gateway
from tests.fakes import FakeEcho  # noqa: F401 — эхо-орган сюжетных приёмок вне этого файла


class FakeReturning:
    """Орган, возвращающий заданный результат — для рефлексии по критерию (W-0027):
    важен сам факт результата, а не эхо payload."""

    def __init__(self, entry: dict[str, Any], result: Any) -> None:
        self.entry = entry
        self.result = result
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def health(self) -> bool:
        return True

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Cost]:
        self.calls.append((tool, payload))
        return self.result, Cost(tokens_in=1, tokens_out=1, seconds=0.01)


def _manifest(tmp_path: Path) -> Path:
    man = {
        "version": "t",
        "organs": [
            {
                "name": "a",
                "system": "s",
                "mode": "dependency",
                "upstream": "u",
                "license": "MIT",
                "transport": "stdio",
                "command": ["x"],
                "tools": ["t"],
                "authority": {"fs": "none", "network": "none", "process": "none"},
            }
        ],
    }
    import yaml

    path = tmp_path / "m.yaml"
    path.write_text(yaml.safe_dump(man), encoding="utf-8")
    return path


def _write_hashed_journal(path: Path, n: int = 3) -> Journal:
    journal = Journal()
    journal.attach(path)
    trace = new_trace_id()
    for i in range(n):
        journal.append(make("act", "synapse", "x", trace, {"n": i}))
    journal.close()
    return journal


# --- W-0026: хэш-цепочка содержимого (SPEC-0003 п.15) ------------------------


def test_new_blood_is_hashed(tmp_path: Path) -> None:
    """Журнал ставит `prev_sha256` сам (как prev_id/stored_at): каждый конверт,
    кроме первого в файле, несёт канонический SHA-256 предыдущей строки файла.
    Изготовитель конверта хэш не выдумывает — журнал печатает при append."""
    path = tmp_path / "blood.jsonl"
    _write_hashed_journal(path)
    lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert "prev_sha256" not in lines[0], "первый конверт файла нечему заверять"
    for prev, cur in zip(lines, lines[1:]):
        assert cur.get("prev_sha256") == canonical_sha256(prev), (
            f"конверт {cur['id'][:8]} не заверяет содержание предыдущего"
        )


def test_content_tampering_is_detected_in_hashed_blood(tmp_path: Path) -> None:
    """Переворот приёмки-предписания F-01 (волна №20): подмена содержимого при
    сохранённых id/prev_id в хэшированной крови ЛОВИТСЯ при чтении — verify
    отчитывается content_gaps, подделка не проходит молча."""
    path = tmp_path / "blood.jsonl"
    _write_hashed_journal(path)

    lines = path.read_text(encoding="utf-8").splitlines()
    forged = json.loads(lines[1])
    forged["payload"] = {"n": 999, "forged": True}
    lines[1] = json.dumps(forged, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = verify(path)
    assert report["chained"] and report["gaps"] == [], "цепочка порядка цела — подмена тоньше"
    assert report["content_gaps"], "хэш-цепочка заверяет содержимое: подмена поймана"


def test_truncation_is_caught_by_anchor(tmp_path: Path) -> None:
    """Внешний якорь против усечения хвоста (F-01/D1): удаление последних строк
    хэш-цепочку оставшегося хвоста не ломает — якорь (seal) помнит, сколько
    событий и каким хэшем был запечатан файл; verify с якорем красит усечение."""
    path = tmp_path / "blood.jsonl"
    _write_hashed_journal(path, n=4)
    anchor = seal(path, name="runs/wave/blood.jsonl")

    truncated = tmp_path / "cut.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    truncated.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")

    report = verify(truncated, anchor=anchor)
    assert report["content_gaps"], "усечение хвоста поймано якорем, не спрятано"
    assert "усеч" in report["content_gaps"][0]["reason"]
    assert verify(path, anchor=anchor)["content_gaps"] == [], "живой файл якорю верен"


def test_tail_substitution_caught_by_anchor(tmp_path: Path) -> None:
    """Подмена последнего конверта целиком (своим prev_sha256) ловится якорем:
    last_id и last_sha256 запечатанного файла не совпадут с подделкой."""
    path = tmp_path / "blood.jsonl"
    _write_hashed_journal(path, n=3)
    anchor = seal(path, name="runs/wave/blood.jsonl")

    lines = path.read_text(encoding="utf-8").splitlines()
    forged = json.loads(lines[-1])
    forged["payload"] = {"forged": "хвост"}
    lines[-1] = json.dumps(forged, ensure_ascii=False)
    forged_path = tmp_path / "forged.jsonl"
    forged_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = verify(forged_path, anchor=anchor)
    assert report["content_gaps"], "подмена хвоста названа якорем"


def test_legacy_blood_stays_valid(tmp_path: Path) -> None:
    """Старая кровь (v0.4–v0.11) без prev_sha256 валидна навсегда: verify не
    требует хэшей там, где их не заявляли — hashed=False, content_gaps нет.
    Граница честности остаётся названной: старый журнал содержимое не заверяет."""
    path = tmp_path / "blood.jsonl"
    trace = new_trace_id()
    envelopes = [
        {
            "id": "11111111-1111-4111-8111-111111111111",
            "ts": "2026-11-01T12:00:00Z",
            "type": "act",
            "source": "brainstem",
            "organ": "self",
            "trace_id": trace,
            "payload": {"n": 1},
            "cost": {"tokens_in": 0, "tokens_out": 0, "seconds": 0.0},
        },
        {
            "id": "22222222-2222-4222-8222-222222222222",
            "ts": "2026-11-01T12:00:01Z",
            "type": "reflect",
            "source": "brainstem",
            "organ": "self",
            "trace_id": trace,
            "prev_id": "11111111-1111-4111-8111-111111111111",
            "payload": {"intent": "работа", "satisfied": True},
            "cost": {"tokens_in": 0, "tokens_out": 0, "seconds": 0.0},
        },
    ]
    path.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in envelopes) + "\n", encoding="utf-8"
    )
    report = verify(path)
    assert report["events"] == 2 and report["chained"] and report["gaps"] == []
    assert report["hashed"] is False and report["content_gaps"] == [], (
        "старая кровь валидна навсегда — verify не выдумывает претензий"
    )


def test_mixed_file_hash_zone(tmp_path: Path) -> None:
    """Смешанный файл: журнал, начатый до W-0026, продолжен после — хэш-зона
    начинается с первого prev_sha256 (наследника старого хвоста), verify чист;
    подмена конверта В хэш-зоне ловится, в старой зоне — граница остаётся
    честно названной (старая кровь без хэшей не заверяется)."""
    path = tmp_path / "blood.jsonl"
    trace = new_trace_id()
    legacy = {
        "id": "33333333-3333-4333-8333-333333333333",
        "ts": "2026-11-01T12:00:00Z",
        "type": "boot",
        "source": "brainstem",
        "organ": "self",
        "trace_id": trace,
        "payload": {},
        "cost": {"tokens_in": 0, "tokens_out": 0, "seconds": 0.0},
    }
    path.write_text(json.dumps(legacy, ensure_ascii=False) + "\n", encoding="utf-8")

    journal = Journal()
    journal.attach(path)
    journal.append(make("act", "synapse", "x", trace, {"n": 1}))
    journal.append(make("act", "synapse", "x", trace, {"n": 2}))
    journal.close()

    lines = path.read_text(encoding="utf-8").splitlines()
    assert "prev_sha256" not in json.loads(lines[0])
    assert "prev_sha256" in json.loads(lines[1]), "наследник старого хвоста начал хэш-зону"
    assert "prev_sha256" in json.loads(lines[2])
    assert verify(path)["content_gaps"] == [], "смешанный файл цел — претензий нет"

    # подмена в хэш-зоне ловится (средний конверт: его хэш изменится —
    # следующий ронёт ссылку; подмена последнего ловится якорем, не цепочкой)
    mutated = json.loads(lines[1])
    mutated["payload"] = {"n": "подмена"}
    lines[1] = json.dumps(mutated, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert verify(path)["content_gaps"], "подмена в заверенной зоне поймана"


def test_dedupe_ignores_file_metadata(tmp_path: Path) -> None:
    """Метаданные файла (prev_id, stored_at, prev_sha256) — не содержание (A01):
    тот же id с тем же эффектом и другим хэшем — dedupe, строка не дублируется;
    тот же id с другим содержанием — конфликт, fail-closed; тот же ключ —
    повторная доставка: возвращается записанное событие."""
    journal = Journal()
    trace = new_trace_id()
    first = journal.append(make("act", "synapse", "x", trace, {"n": 1}, idempotency_key="k1"))
    again = journal.append(make("act", "synapse", "x", trace, {"n": 1}, idempotency_key="k1"))
    assert again["id"] == first["id"] and len(journal) == 1, "повтор — dedupe, строка одна"

    meta = dict(first)
    meta["prev_sha256"] = "f" * 64  # другой якорь — всё ещё то же содержание
    assert journal.append(meta)["id"] == first["id"] and len(journal) == 1, (
        "метаданные файла не путают дедуп"
    )

    conflict = dict(first)
    conflict["payload"] = {"n": 999}  # тот же id, другое содержание — не dedupe
    with pytest.raises(EnvelopeError):
        journal.append(conflict)


def test_bad_hash_format_is_fail_closed(tmp_path: Path) -> None:
    """Битый prev_sha256 (не 64 hex) роняется при записи ДО крови — схема
    fail-closed, как для неизвестных классов trust/privacy (ADR-0014).
    Проба на новом конверте: записанный журнал вернул бы по дедупу, не глядя."""
    path = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.attach(path)
    trace = new_trace_id()
    journal.append(make("act", "synapse", "x", trace, {"n": 1}))
    forged = make("act", "synapse", "x", trace, {"n": 2})  # новый id — не дедуп
    forged["prev_sha256"] = "не-хэш"
    with pytest.raises(EnvelopeError):
        journal.append(forged)
    journal.close()
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1, "подделка не дошла до файла"


def test_resume_continues_hash_chain(tmp_path: Path) -> None:
    """Resume (п.8): сессия, открывшая журнал заново (from_jsonl), продолжает
    хэш-цепочку — новый конверт заверяет последний конверт файла, разрыва
    и рассинхрона нет."""
    path = tmp_path / "blood.jsonl"
    _write_hashed_journal(path, n=2)

    resumed = Journal.from_jsonl(path)
    trace = resumed.all()[0]["trace_id"]
    resumed.append(make("act", "synapse", "x", trace, {"n": 3}))
    lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert lines[-1]["prev_sha256"] == canonical_sha256(lines[-2]), (
        "resume шьёт и содержимое, не только порядок"
    )
    report = verify(path)
    assert report["gaps"] == [] and report["content_gaps"] == []


# --- W-0027: REFLECT по проверяемому критерию (SPEC-0001 v0.3.0) --------------


def _run_step(tmp_path: Path, result: Any, accept: Any) -> tuple[bool, Journal]:
    journal = Journal()
    gateway = Gateway(str(_manifest(tmp_path)), journal)
    gateway.bind_adapter("a", FakeReturning({"name": "a"}, result))
    loop = Loop(gateway, journal)
    ok = loop.run([Step("a", "t", {"q": 1}, intent="работа", accept=accept)])
    return ok, journal


def test_error_result_not_satisfied_by_schema(tmp_path: Path) -> None:
    """Зеркало F-06/D2: орган вернул {'error':…, 'ok': false}, шаг объявил
    JSON-схему успеха — результат НЕ принят, run() False, трейс завершён halt
    (G1), reflect честно называет провал."""
    ok, journal = _run_step(
        tmp_path,
        {"error": "сломалось", "ok": False},
        accept={"type": "object", "required": ["ok"], "properties": {"ok": {"const": True}}},
    )
    assert ok is False, "критерий шага объявлен — «error с ok:false» не успех"
    reflect = journal.by_type("reflect")[0]
    assert reflect["payload"]["satisfied"] is False
    halt = journal.by_type("halt")
    assert halt and "не удовлетворено" in halt[0]["payload"]["reason"], "G1: трейс полон"


def test_schema_valid_result_is_satisfied(tmp_path: Path) -> None:
    """Результат, принятый схемой шага, — удовлетворённое намерение."""
    ok, journal = _run_step(
        tmp_path,
        {"ok": True, "data": [1, 2]},
        accept={"type": "object", "required": ["ok"], "properties": {"ok": {"const": True}}},
    )
    assert ok is True
    assert journal.by_type("reflect")[0]["payload"]["satisfied"] is True


def test_predicate_accept(tmp_path: Path) -> None:
    """Предикат-критерий: короткая функция над результатом решает приёмку."""
    ok_true, _ = _run_step(tmp_path, {"sum": 100}, accept=lambda r: r.get("sum", 0) > 0)
    ok_false, journal = _run_step(tmp_path, {"sum": 0}, accept=lambda r: r.get("sum", 0) > 0)
    assert ok_true is True
    assert ok_false is False
    assert journal.by_type("reflect")[0]["payload"]["satisfied"] is False


def test_broken_predicate_halts_with_reason(tmp_path: Path) -> None:
    """Критерий упал исключением — это дефект плана, не органа: результат не
    принят, причина названа, трейс завершён halt (G1), эффект не спрятан."""
    def broken(_: Any) -> bool:
        raise KeyError("критерий сломан")

    ok, journal = _run_step(tmp_path, {"ok": True}, accept=broken)
    assert ok is False
    reflect = journal.by_type("reflect")[0]
    assert reflect["payload"]["satisfied"] is False
    assert "критерий" in reflect["payload"].get("reason", ""), "причина провала названа"
    assert journal.by_type("halt"), "G1: трейс полон"


def test_unknown_criterion_is_fail_closed(tmp_path: Path) -> None:
    """Критерий, который цикл не понимает (ни схема, ни предикат), — halt с
    причиной, не молчаливое применение старой рефлексии."""
    ok, journal = _run_step(tmp_path, {"ok": True}, accept="строка-вместо-критерия")
    assert ok is False
    assert "критерий" in journal.by_type("halt")[0]["payload"]["reason"]


def test_m1_default_unchanged(tmp_path: Path) -> None:
    """Без критерия — прежняя рефлексия M1 (аддитивно): результат есть —
    удовлетворено, пустой результат — halt. Старые планы валидны навсегда."""
    ok_true, _ = _run_step(tmp_path, {"любой": "результат"}, accept=None)
    ok_false, journal = _run_step(tmp_path, None, accept=None)
    assert ok_true is True
    assert ok_false is False
    reflect = journal.by_type("reflect")[0]
    assert reflect["payload"]["satisfied"] is False
    assert "criterion" in reflect["payload"], "кровь называет, чем мерили (m1)"


def test_criterion_named_in_reflect(tmp_path: Path) -> None:
    """Кровь честная: reflect называет критерий приёмки — schema/predicate —
    читатель крови видит, ЧЕМ намерение мерилось, а не только вердикт."""
    _, journal_schema = _run_step(tmp_path, {"ok": True}, accept={"type": "object"})
    _, journal_pred = _run_step(tmp_path, {"ok": True}, accept=lambda r: True)
    assert journal_schema.by_type("reflect")[0]["payload"]["criterion"] == "jsonschema"
    assert journal_pred.by_type("reflect")[0]["payload"]["criterion"] == "predicate"
