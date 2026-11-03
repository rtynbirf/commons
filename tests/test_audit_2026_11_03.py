# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмки волны №20 — верификация советов коллег (внешний аудит 2026-11-03).

Коллеги прислали аудит с находками и патчем. Правило дома: совет — не факт,
факт — замер на живом коде. Все пробы коллег подтверждены живьём на HEAD 0.38.0
до правок (проба `runs/2026-11-03-wave20-colleague-verification/`), здесь —
приёмки закрытия: F-02 (кровь не принимает несериализуемое, SPEC-0003 п.14),
F-03 (эффект без крови завершён halt, SPEC-0001 G1), F-04/F-05 (полная
грамматика мутаций и чтения каталогов, SPEC-0002 п.8 v0.11.0). F-01 — не
закрывается кодом, а честно называется границей (тест-документация ниже):
защита содержимого — хотёлка W-0026.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from blood.envelope import EnvelopeError, Cost, make, new_trace_id
from blood.journal import Journal, verify
from brainstem.loop import Loop, Step
from synapse.authority import AuthorityViolation, enforce, normalize
from synapse.gateway import BloodRecordError, Gateway
from tests.fakes import FakeEcho


# --- F-02: кровь не принимает несериализуемое (SPEC-0003 п.14) ---


def test_unserializable_envelope_changes_nothing(tmp_path: Path) -> None:
    """Несериализуемый payload — EnvelopeError ДО мутации: ни строки, ни памяти,
    ни цепочки; следующий валидный append продолжает её без разрыва."""
    path = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.attach(path)
    trace = new_trace_id()
    journal.append(make("act", "synapse", "x", trace, {"ok": 1}))
    before = len(journal)
    with pytest.raises(EnvelopeError):
        journal.append(make("act", "synapse", "x", trace, {"raw": b"bytes"}))
    assert len(journal) == before, "память не хранит конверт, которого нет в файле"
    journal.append(make("act", "synapse", "x", trace, {"ok": 2}))
    journal.close()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2, "файл не содержит битой строки"
    report = verify(path)
    assert report["gaps"] == [] and report["chained"], "цепочка жива после отказа записи"


def test_unserializable_envelope_with_journalled_journal(tmp_path: Path) -> None:
    """Тот же отказ без файла (журнал в памяти): память тоже не мутируется —
    память крови — свёртка файла, а не его обогащение (SPEC-0003 п.14)."""
    journal = Journal()
    trace = new_trace_id()
    journal.append(make("act", "synapse", "x", trace, {"ok": 1}))
    with pytest.raises(EnvelopeError):
        journal.append(make("act", "synapse", "x", trace, {"raw": bytearray(b"x")}))
    assert len(journal) == 1
    assert journal.totals(trace).tokens_in >= 0  # счёт жив, рассинхрона нет


# --- F-01: честная граница цепочки (не закрывается кодом — документируется) ---


def test_chain_boundary_content_tampering_is_not_detected(tmp_path: Path) -> None:
    """Приёмка-документация границы (SPEC-0003 п.14): подмена содержимого при
    сохранённых id/prev_id проходит verify — цепочка шьёт порядок, а не байты.
    НЕ скрываем и не притворяемся: граница названа в спеке и докстринге,
    защита содержимого — хотёлка W-0026 (prev_sha256). При её служении этот
    тест переворачивается честно — как приёмка-предписание волны №13."""
    path = tmp_path / "blood.jsonl"
    journal = Journal()
    journal.attach(path)
    trace = new_trace_id()
    for i in range(3):
        journal.append(make("act", "synapse", "x", trace, {"n": i}))
    journal.close()

    lines = path.read_text(encoding="utf-8").splitlines()
    forged = json.loads(lines[1])
    forged["payload"] = {"n": 999, "forged": True}
    lines[1] = json.dumps(forged, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = verify(path)
    assert report["chained"] and report["gaps"] == [], (
        "граница жива: verify не заверяет содержимое (W-0026 закроет — тест перевернётся)"
    )


# --- F-04: полная грамматика файловых мутаций (SPEC-0002 п.8 v0.11.0) ---


@pytest.mark.parametrize("op", ["truncate", "symlink", "link", "utime", "setxattr"])
def test_guard_blocks_fs_mutations_under_read_only(tmp_path: Path, op: str) -> None:
    """Мутации вне исходной грамматики (F-04) прерваны при fs: read-only:
    файл-жертва остаётся нетронут (содержимое, метки времени, имя)."""
    victim = tmp_path / "victim.txt"
    victim.write_text("данные")
    outside = tmp_path / "out"
    outside.mkdir()
    actions = {
        "truncate": lambda: os.truncate(victim, 0),
        "symlink": lambda: os.symlink(victim, outside / "ln"),
        "link": lambda: os.link(victim, outside / "hl"),
        "utime": lambda: os.utime(victim, (0, 0)),
        "setxattr": lambda: os.setxattr(victim, "user.a", b"1"),
    }
    guard = normalize({"fs": "read-only", "network": "none", "process": "none"})
    with pytest.raises(AuthorityViolation):
        with enforce(guard, organ="probe"):
            actions[op]()
    assert victim.read_text() == "данные"
    assert (outside / "ln").exists() is False
    assert (outside / "hl").exists() is False


def test_guard_symlink_target_outside_roots_is_goal_check(tmp_path: Path) -> None:
    """Скоуп read-write: symlink проверяется по СОЗДАВАЕМОЙ ссылке (второй
    аргумент), цель ссылки — произвольный текст (свойство symlink, названное
    честно в SPEC-0002 п.8 v0.11.0); ссылка вне корней — прервана."""
    roots = tmp_path / "roots"
    roots.mkdir()
    victim = roots / "victim.txt"
    victim.write_text("данные")
    guard = normalize({"fs": {"mode": "read-write", "paths": [str(roots)]}, "network": "none", "process": "none"})
    with pytest.raises(AuthorityViolation):
        with enforce(guard, organ="probe"):
            os.symlink(str(victim), tmp_path / "escape")
    # внутри корней ссылка жива — и цель её может указывать куда угодно (свойство symlink)
    with enforce(guard, organ="probe"):
        os.symlink(str(tmp_path / "outside-target"), roots / "inside-link")
    assert (roots / "inside-link").is_symlink()
    assert (tmp_path / "escape").exists() is False


# --- F-05: чтение структуры каталогов (SPEC-0002 п.8 v0.11.0) ---


def test_guard_blocks_directory_listing_under_fs_none(tmp_path: Path) -> None:
    """os.listdir/os.scandir при fs: none — нарушение (утечка структуры
    каталогов, F-05), кроме рантайма Python; read-only — чтение живо."""
    listing = tmp_path / "docs"
    listing.mkdir()
    (listing / "file.txt").write_text("x")
    strict = normalize({"fs": "none", "network": "none", "process": "none"})
    with pytest.raises(AuthorityViolation):
        with enforce(strict, organ="probe"):
            os.listdir(listing)
    with pytest.raises(AuthorityViolation):
        with enforce(strict, organ="probe"):
            os.scandir(listing)
    ro = normalize({"fs": "read-only", "network": "none", "process": "none"})
    with enforce(ro, organ="probe"):
        assert "file.txt" in os.listdir(listing)


def test_guard_scoped_listing_outside_roots_blocked(tmp_path: Path) -> None:
    """Скоуп fs: listdir/scandir — только внутри заявленных корней (realpath)."""
    roots = tmp_path / "roots"
    roots.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    guard = normalize({"fs": {"mode": "read-only", "paths": [str(roots)]}, "network": "none", "process": "none"})
    with pytest.raises(AuthorityViolation):
        with enforce(guard, organ="probe"):
            os.listdir(outside)
    with enforce(guard, organ="probe"):
        os.listdir(roots)  # внутри корней — живо


# --- F-03: эффект без крови завершён halt (SPEC-0001 G1) ---


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
    path = tmp_path / "m.yaml"
    import yaml

    path.write_text(yaml.safe_dump(man), encoding="utf-8")
    return path


class _ActStranglingJournal(Journal):
    """Журнал, не принимающий act: имитация отказа записи ПОСЛЕ вызова органа
    (диск, конфликт, что угодно — для ствола важен сам факт)."""

    def append(self, envelope: dict) -> dict:
        if envelope.get("type") == "act":
            raise EnvelopeError("приёмка F-03: запись act упала")
        return super().append(envelope)


def test_unserializable_step_payload_never_reaches_organ(tmp_path: Path) -> None:
    """Проверка ДО факта (F-03): несериализуемый payload шага роняется halt'ом
    ДО invoke — орган не вызван, эффект не случился, кровь без act (закон 2)."""
    journal = Journal()
    gateway = Gateway(str(_manifest(tmp_path)), journal)
    gateway.bind_adapter("a", FakeEcho({"name": "a"}))
    loop = Loop(gateway, journal)

    ok = loop.run([Step("a", "t", {"raw": b"bytes"}, intent="байты")])

    assert ok is False, "несериализуемый payload — halt, не исключение"
    assert [e["type"] for e in journal.by_trace(journal.all()[0]["trace_id"])].count("act") == 0, \
        "орган не вызван — эффекта без крови нет"
    assert journal.by_type("halt") and "не сериализуется" in journal.by_type("halt")[0]["payload"]["reason"]


def test_act_write_failure_halts_trace(tmp_path: Path) -> None:
    """Отказ записи act ПОСЛЕ invoke (F-03): орган отработал — кровь называет
    это error-конвертом шлюза, ствол завершает трейс halt'ом (G1), run()
    возвращает False и не бросает наружу."""
    journal = _ActStranglingJournal()
    gateway = Gateway(str(_manifest(tmp_path)), journal)
    adapter = FakeEcho({"name": "a"})
    gateway.bind_adapter("a", adapter)
    loop = Loop(gateway, journal)

    ok = loop.run([Step("a", "t", {"ok": 1}, intent="работа")])

    assert ok is False, "отказной выход завершён halt (G1)"
    halt = journal.by_type("halt")[0]["payload"]["reason"]
    assert "эффект без крови" in halt
    error = [e for e in journal.by_type("error") if "эффект без крови" in e["payload"].get("reason", "")]
    assert error, "шлюз назвал эффект без крови error-конвертом — не спрятан"
    assert len(adapter.calls) == 1, "орган отработал — факт назван, не спрятан"
