# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Приёмка SPEC-0002 v0.6.0 «страж и потоки» (волна №11): наследование стража, `__pycache__`.

Слепая зона волны №7 (строки 34–35 отчёта): страж на contextvar — поток, рождённый
внутри `invoke`, получает чистый контекст, страж там не активен, ренегат выносит
нарушение за границу полномочий молча. Эти тесты фиксируют КОНТРАКТ спеки:
полномочия органа связывают код органа, а не поток исполнения.

Граница действия (не дыра, SPEC-0002 п.8 v0.6.0): поток, рождённый ВНЕ вызова,
стража не имеет; страж закрепляется за потоком на момент рождения.

Мини-манифесты собираются в tmp_path внутри тестов: conftest-манифест не тронут.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
import yaml

from blood.journal import Journal
from synapse.authority import AuthorityViolation, enforce
from synapse.gateway import Gateway

from .fakes import FakeThreadedRenegade  # noqa: TID252

READ_ONLY = {"fs": "read-only", "network": "none", "process": "none"}


def _organ(name: str, *, adapter: str, tools: list[str], authority: dict[str, Any]) -> dict[str, Any]:
    """Мини-запись манифеста со всеми обязательными полями (SPEC-0002 п.1)."""
    return {
        "name": name,
        "system": "senses",
        "mode": "dependency",
        "upstream": f"https://example.invalid/{name}",
        "license": "MIT",
        "transport": "stdio",
        "command": f"{name}-mcp",
        "healthcheck": "initialize handshake",
        "tools": tools,
        "authority": authority,
        "adapter": adapter,
    }


def _gateway(tmp_path: Path, journal: Journal, organs: list[dict[str, Any]]) -> Gateway:
    path = tmp_path / "mcp-manifest.yaml"
    path.write_text(
        yaml.safe_dump({"organs": organs, "substitutions": {}}, allow_unicode=True),
        encoding="utf-8",
    )
    return Gateway(path, journal)


def _adapter(gateway: Gateway, kind: type) -> Any:
    found = [a for a in gateway.adapters if isinstance(a, kind)]
    assert found, f"шлюз не собрал адаптер {kind.__name__}"
    return found[0]


# --- a) ренегат в потоке: syscall прерван, файла нет --------------------------


def test_thread_escape_blocked(tmp_path: Path) -> None:
    """Поток, рождённый под стражем, наследует его: запись из потока прервана, файла нет (п.8 v0.6.0)."""
    target = tmp_path / "smuggled.txt"
    caught: list[BaseException] = []

    with enforce(READ_ONLY, organ="threaded-renegade"):
        def crime() -> None:
            try:
                with open(target, "w", encoding="utf-8") as fh:
                    fh.write("контрабанда из потока")
            except BaseException as exc:  # честный поток: нарушение не глотается
                caught.append(exc)

        worker = threading.Thread(target=crime, name="escape-probe")
        worker.start()
        worker.join(timeout=5)

    assert caught and isinstance(caught[0], AuthorityViolation), (
        f"страж не активен в потоке-наследнике: нарушение не прервано (caught={caught!r})"
    )
    assert "threaded-renegade" in str(caught[0]), "нарушение в потоке потеряло имя органа"
    assert not target.exists(), "страж пропустил запись из потока: контрабанда на диске"


# --- b) шлюз: ренегат-в-потоке отдаёт security.violation в кровь --------------


def test_gateway_threaded_renegade_in_blood(tmp_path: Path, journal: Journal) -> None:
    """Приёмка: ренегат в потоке прерван, честный орган отдаёт нарушение — в крови security.violation, не act."""
    target = tmp_path / "smuggled-thread.txt"
    gateway = _gateway(
        tmp_path,
        journal,
        [_organ("threaded", adapter="tests.fakes:FakeThreadedRenegade", tools=["smuggle_in_thread"], authority=READ_ONLY)],
    )
    renegade = _adapter(gateway, FakeThreadedRenegade)

    with pytest.raises(AuthorityViolation):
        gateway.call("threaded", "smuggle_in_thread", {"path": str(target)}, "auth-threads")

    assert not target.exists(), "запись из потока легла на диск"
    assert renegade.thread_errors and isinstance(renegade.thread_errors[0], AuthorityViolation), (
        "нарушение не дошло до потока"
    )
    (violation,) = journal.by_type("security.violation")
    assert violation["organ"] == "threaded" and violation["trace_id"] == "auth-threads"
    assert not journal.by_type("act"), "нарушенный вызов не должен попадать в кровь как act"


# --- c) вложенные потоки: внук тоже под стражем --------------------------------


def test_grandchild_thread_inherits(tmp_path: Path) -> None:
    """Поток, рождённый в потоке-наследнике (внук), тоже под стражем (п.8 v0.6.0, приёмка)."""
    target = tmp_path / "grandchild.txt"
    caught: list[BaseException] = []

    with enforce(READ_ONLY, organ="grandpa"):
        def child() -> None:
            def crime() -> None:
                try:
                    with open(target, "w", encoding="utf-8") as fh:
                        fh.write("контрабанда внука")
                except BaseException as exc:
                    caught.append(exc)

            worker = threading.Thread(target=crime, name="grandchild-probe")
            worker.start()
            worker.join(timeout=5)

        middle = threading.Thread(target=child, name="child-probe")
        middle.start()
        middle.join(timeout=5)

    assert caught and isinstance(caught[0], AuthorityViolation), f"внук без стража (caught={caught!r})"
    assert not target.exists()


# --- d) подкласс Thread с run() тоже наследует ---------------------------------


def test_thread_subclass_run_inherits(tmp_path: Path) -> None:
    """Подкласс Thread, переопределяющий run() без target, наследует стража (п.8 v0.6.0)."""
    target = tmp_path / "subclass.txt"
    caught: list[BaseException] = []

    class Criminal(threading.Thread):
        def run(self) -> None:
            try:
                with open(target, "w", encoding="utf-8") as fh:
                    fh.write("контрабанда подкласса")
            except BaseException as exc:
                caught.append(exc)

    with enforce(READ_ONLY, organ="subclass-renegade"):
        criminal = Criminal(name="subclass-probe")
        criminal.start()
        criminal.join(timeout=5)

    assert caught and isinstance(caught[0], AuthorityViolation), f"подкласс без стража (caught={caught!r})"
    assert not target.exists()


# --- e) пул с ленивым стартом внутри вызова наследует ---------------------------


def test_pool_lazy_start_inherits(tmp_path: Path) -> None:
    """ThreadPoolExecutor, чьи рабочие стартовали при первом submit внутри вызова, наследует стража (п.8 v0.6.0)."""
    target = tmp_path / "pool.txt"
    caught: list[BaseException] = []

    with enforce(READ_ONLY, organ="pool-renegade"):
        with ThreadPoolExecutor(max_workers=1) as pool:  # рабочие стартуют на submit — под стражем
            future = pool.submit(
                lambda: _try_write(target, caught)
            )
            future.result(timeout=5)

    assert caught and isinstance(caught[0], AuthorityViolation), f"пул без стража (caught={caught!r})"
    assert not target.exists()


def _try_write(target: Path, caught: list[BaseException]) -> None:
    try:
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("контрабанда из пула")
    except BaseException as exc:
        caught.append(exc)


# --- f) граница действия: поток вне вызова стража не имеет (не дыра) ------------


def test_thread_outside_invoke_not_guarded(tmp_path: Path) -> None:
    """Граница действия (п.8 v0.6.0): поток, рождённый ВНЕ enforce, стража не имеет — задокументировано."""
    target = tmp_path / "outside.txt"
    done = threading.Event()

    def honest_work() -> None:
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("не орган: обычный код процесса")
        done.set()

    worker = threading.Thread(target=honest_work, name="outside-probe")
    worker.start()
    worker.join(timeout=5)
    assert done.is_set() and target.exists(), "обычный поток процесса сломан"


# --- g) pycache: нарушение называет предписание ---------------------------------


def test_pycache_write_names_prescription(tmp_path: Path) -> None:
    """Ленивый импорт пишет `__pycache__` при read-only — нарушение с предписанием «прогрейте импорты» (п.8 v0.6.0)."""
    pycache = tmp_path / "__pycache__" / "organ_lazy.pyc"
    pycache.parent.mkdir()

    with enforce(READ_ONLY, organ="lazy-importer"):
        with pytest.raises(AuthorityViolation) as exc_info:
            with open(pycache, "wb") as fh:  # имитация ленивого импорта внутри invoke
                fh.write(b"\x00bytecode")

    text = str(exc_info.value)
    assert "прогрейте импорты" in text, f"текст нарушения не называет средство: {text!r}"
    assert not pycache.exists()
