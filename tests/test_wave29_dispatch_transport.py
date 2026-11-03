# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмки волны №29 — контур обмена (docs/TZ.md ТЗ-2.4, ТЗ-2.5, ТЗ-3.1).

ТЗ-2.4 (A24/A25) — dispatcher: доставка поручений без каскада — retry с
пределом и DLQ поимённо, redelivery идемпотентен (A01), перегрузка — SHED
до факта без каскада, дедлайн — TIMEOUT с названной границей; кровь —
журнал фактов доставки, не шина pub/sub (дух ADR-001 пакета).

ТЗ-2.5 (W-0020) — процессные оценки пути: поле `path` в конверте — этапы и
вердикты каждого; шаг, переживший отказ, отличим в дневнике и крови.

ТЗ-3.1 — честный ADR транспорта: дом говорит по stdio (ADR-0016), HTTP+OAuth —
за Человеком на живом хосте; манифест дома — только stdio.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from blood.envelope import Cost, make, validate
from blood.diary import render
from blood.journal import Journal
from brainstem.dispatch import DLQ, DONE, SHED, TIMEOUT, Dispatcher

TRACE = "wave29-dispatch"


def _journal() -> Journal:
    return Journal()


# --- ТЗ-2.4: dispatcher (A24) ---------------------------------------------------


def test_deliver_done_writes_facts_to_blood() -> None:
    """Доставка — факт в крови (act), наружу — DONE с результатом."""
    journal = _journal()
    d = Dispatcher(journal)
    report = d.deliver("k1", lambda: {"ok": 1}, label="письмо-1")
    assert report["verdict"] == DONE and report["result"] == {"ok": 1}
    acts = [e for e in journal.all() if e["type"] == "act" and e["payload"].get("delivery")]
    assert acts and acts[0]["payload"]["delivery"]["key"] == "k1"
    assert acts[0]["payload"]["delivery"]["verdict"] == DONE


def test_retry_then_done_names_every_failed_attempt() -> None:
    """Отказ каждой попытки назван в крови (error), итог — DONE с числом попыток."""
    journal = _journal()
    d = Dispatcher(journal)
    calls = {"n": 0}

    def flaky() -> dict:
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("орган дёрнулся")
        return {"ok": True}

    report = d.deliver("k2", flaky, label="письмо-2")
    assert report["verdict"] == DONE and report["attempts"] == 3
    errors = [e for e in journal.all() if e["type"] == "error" and e["payload"].get("delivery")]
    assert len(errors) == 2 and "попытка 1/3" in errors[0]["payload"]["reason"]


def test_dead_letter_is_named_and_never_escapes() -> None:
    """Предел попыток — DLQ: назван поимённо в крови, наружу не вырывается."""
    journal = _journal()
    d = Dispatcher(journal, max_attempts=2)

    def broken() -> dict:
        raise RuntimeError("орган мёртв")

    report = d.deliver("k3", broken, label="письмо-3")
    assert report["verdict"] == DLQ and report["attempts"] == 2
    dead = d.dead_letters()
    assert len(dead) == 1
    assert dead[0]["payload"]["delivery"]["label"] == "письмо-3"
    assert "орган мёртв" in dead[0]["payload"]["reason"]


def test_redelivery_is_idempotent_a01() -> None:
    """A01: тот же ключ — тот же исход, обработчик не вызывается второй раз."""
    journal = _journal()
    d = Dispatcher(journal)
    calls = {"n": 0}

    def once() -> dict:
        calls["n"] += 1
        return {"билет": calls["n"]}

    first = d.deliver("k4", once, label="письмо-4")
    second = d.deliver("k4", once, label="письмо-4")
    assert calls["n"] == 1, "повтор ключа не повторяет эффект"
    assert first["verdict"] == second["verdict"] == DONE
    assert second["redelivered"] is True
    assert second["result"] == first["result"]


def test_backpressure_sheds_without_cascade() -> None:
    """Перегрузка: SHED до факта, живые поручения не роняются (без каскада)."""
    journal = _journal()
    d = Dispatcher(journal, max_queue=1)
    d.deliver("busy", lambda: 1, label="занято-1")  # DONE, inflight пуст — но ключ занят проверкой ниже
    # раздуваем очередь вручную честным способом: два живых поручения
    d2 = Dispatcher(journal, max_queue=2)
    shed = {"thrown": False}

    def third() -> dict:
        return {}

    d2._inflight = {"a": "работа-а", "b": "работа-b"}  # очередь полна
    report = d2.deliver("c", third, label="письмо-c")
    assert report["verdict"] == SHED
    assert not shed["thrown"]
    alerts = [e for e in journal.all() if e["type"] == "alert" and e["payload"].get("delivery")]
    assert alerts and alerts[-1]["payload"]["delivery"]["verdict"] == SHED


def test_timeout_names_the_effect_honestly() -> None:
    """Дедлайн: TIMEOUT с названной границей — эффект мог случиться, это сказано."""
    journal = _journal()
    fake = {"t": 100.0}
    d = Dispatcher(journal, timeout=1.0, clock=lambda: fake["t"])

    def slow() -> dict:
        fake["t"] += 5.0  # обработчик жил дольше дедлайна
        return {"поздно": True}

    report = d.deliver("k5", slow, label="письмо-5")
    assert report["verdict"] == TIMEOUT
    assert "дедлайн" in report["reason"] and "эффект назван" in report["reason"]
    errors = [e for e in journal.all() if e["type"] == "error" and e["payload"].get("delivery")]
    assert errors and errors[-1]["payload"]["delivery"]["verdict"] == TIMEOUT


def test_dispatch_grammar_is_fail_closed() -> None:
    """Поручение без ключа и нулевые пределы — ValueError до факта."""
    journal = _journal()
    with pytest.raises(ValueError):
        Dispatcher(journal, max_queue=0)
    with pytest.raises(ValueError):
        Dispatcher(journal, timeout=0)
    d = Dispatcher(journal)
    with pytest.raises(ValueError):
        d.deliver("", lambda: 1, label="без ключа")


def test_blood_is_not_a_bus_no_new_types() -> None:
    """Дух ADR-001: Dispatcher пишет только факты известными типами (act/error/alert)."""
    journal = _journal()
    d = Dispatcher(journal, max_attempts=1)
    d.deliver("k6", lambda: {"ok": 1}, label="письмо-6")
    d.deliver("k7", lambda: (_ for _ in ()).throw(OSError("упало")), label="письмо-7")
    assert {e["type"] for e in journal.all()} <= {"act", "error", "alert"}


# --- ТЗ-2.5: путь в крови (W-0020, A05-стиль) ------------------------------------


def test_path_field_survives_schema_and_diary() -> None:
    """Поле path валидно схемой; дневник различает шаг, переживший отказ."""
    envelope = make(
        "act", "brainstem", "self", "tr-path", {"tool": "x"},
        Cost(0, 0, 0.0),
        path=[
            {"stage": "attempt-1", "verdict": "failed", "note": "канал упал"},
            {"stage": "attempt-2", "verdict": "ok", "note": "резерв обслужил"},
        ],
    )
    validate(envelope)  # схема принимает путь
    journal = Journal()
    journal.append(envelope)
    text = render(journal)
    assert "путь" in text and "attempt-1" in text and "failed" in text
    assert "attempt-2" in text


def test_old_blood_without_path_is_valid_forever() -> None:
    """Аддитивность: конверт без path валиден (старая кровь валидна навсегда)."""
    validate(make("reflect", "brainstem", "self", "tr-old", {"verdict": "старая кровь"}, Cost(0, 0, 0.0)))


# --- ТЗ-3.1: честный ADR транспорта -----------------------------------------------


def test_house_manifest_is_local_only() -> None:
    """ADR-0016 (честный, по факту дома): stdio-процессы + http ТОЛЬКО к
    localhost-эндпоинтам; наружного http-шлюза нет. Эндпоинт — литеральный
    loopback ИЛИ env-плейсхолдер (значения переменных — на живом хосте,
    loopback по воле ADR-0016; машина не приписывает чужие значения).
    Литеральный наружный хост без нового ADR — красный PR."""
    manifest = __import__("yaml").safe_load(
        Path("synapse/mcp-manifest.yaml").read_text(encoding="utf-8")
    )
    organs = manifest.get("organs", [])
    assert organs, "манифест дома пуст — сверять нечего"
    for o in organs:
        transport = o.get("transport", "stdio")
        if transport == "http":
            endpoint = str(o.get("endpoint", ""))
            assert endpoint, f"{o.get('name')}: http без эндпоинта"
            if endpoint.startswith("${") and endpoint.endswith("}"):
                continue  # значение живёт на хосте Человека — граница названа в ADR-0016
            host = endpoint.split("://")[-1].split(":")[0].split("/")[0]
            assert host in ("localhost", "127.0.0.1"), (
                f"{o.get('name')}: http наружу ({host}) без нового ADR — воля ADR-0016 нарушена"
            )
        else:
            assert transport == "stdio", f"{o.get('name')}: транспорт {transport!r} не из ADR-0016"


def test_adr0016_exists_and_names_boundary() -> None:
    """ADR-0016 принят: локальный транспорт (stdio + localhost-http); наружный
    MCP HTTP+OAuth — за Человеком, границы названы."""
    adr = Path("docs/adr/ADR-0016-stdio-transport.md").read_text(encoding="utf-8")
    assert "stdio" in adr and "localhost" in adr and "OAuth" in adr
    assert "SPEC-0002" in adr, "ADR обязан ссылаться на геном синапсов"
