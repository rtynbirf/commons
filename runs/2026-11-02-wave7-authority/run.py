# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Живой прогон волны №7 «исполнение полномочий» — SPEC-0002 v0.4.0, пп.8–9.

Пять красных находок аудита волны №5 получают живой ответ (W-0016):

- сцена 1: ренегат с полномочиями `fs: read-only` пытается записать файл —
  страж прерывает вызов ДО записи, `security.violation` в крови, файл не создан;
- сцена 2: ренегат с `network: none` пытается соединиться — прерван до сетевого
  вызова, `security.violation` в крови;
- сцена 3: `AuthorityViolation` сквозь цикл: `run()` = False без исключения,
  кровь трейса полна (plan → security.violation → reflect → halt) — G1;
- сцена 4: замена при invoke-падении (`organ.replace`) + отказ самозванцу и
  безымянному при привязке (п.9) — прежняя привязка не тронута;
- сцена 5: грамматика полномочий fail-closed: неисполнимые ярлыки прошлого
  (`read-only-input-dir`, `walrus`, пустой `hosts`) не дают шлюзу стартовать;
  живой манифест дома стартует.

Кровь — runs/2026-11-02-wave7-authority/blood.jsonl (append-only, порядок сцен =
порядок строк). Скрипт печатает факты, не предсказания: [ЗЕЛЁНО]/[КРАСНО]/[ФАКТ].

Запуск из корня репо: python runs/2026-11-02-wave7-authority/run.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

import yaml  # noqa: E402

from blood.envelope import validate  # noqa: E402
from blood.journal import Journal  # noqa: E402
from brainstem import Loop, Step  # noqa: E402
from synapse.gateway import AuthorityViolation, Gateway, GatewayConfigError  # noqa: E402
from tests.fakes import FakeEcho, FakeFallen, FakeRenegade  # noqa: E402

RUN_DIR = Path(__file__).resolve().parent
BLOOD_PATH = RUN_DIR / "blood.jsonl"

VERDICTS: list[str] = []


def verdict(kind: str, text: str) -> None:
    marker = {"g": "[ЗЕЛЁНО]", "r": "[КРАСНО]", "f": "[ФАКТ]"}[kind]
    line = f"{marker} {text}"
    print(line)
    VERDICTS.append(line)


def manifest_file(tmp: Path, organs: list[dict[str, Any]], subs: dict[str, list[str]] | None = None) -> Path:
    doc = {"version": "w7", "updated": "2026-11-02", "transport_default": "stdio", "organs": organs}
    if subs:
        doc["substitutions"] = subs
    path = tmp / "mcp-manifest.yaml"
    path.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return path


def entry(name: str, adapter_cls: str, *, tools: list[str] | None = None,
          authority: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "system": "senses",
        "mode": "dependency",
        "upstream": f"fake://wave7/{name}",
        "license": "MIT",
        "transport": "stdio",
        "command": "fake",
        "healthcheck": "initialize handshake",
        "tools": tools or ["echo"],
        "authority": authority or {"fs": "read-only", "network": "none", "process": "none"},
        "adapter": adapter_cls,
    }


def types_of(journal: Journal, trace_id: str) -> list[str]:
    return [e["type"] for e in journal.by_trace(trace_id)]


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="wave7-"))
    journal = Journal()
    journal.attach(BLOOD_PATH)  # кровь на диске в момент события (SPEC-0004 п.5)
    try:
        # --- сцена 1: ренегат fs: read-only ---
        contraband = tmp / "contraband.txt"
        renegade_entry = entry(
            "renegade", "tests.fakes:FakeRenegade",
            tools=["smuggle_file", "phone_home", "read_thing"],
        )
        path1 = manifest_file(tmp, [renegade_entry])
        gw1 = Gateway(path1, journal)
        trace1 = "w7-scene1-fs"
        interrupted = False
        try:
            gw1.call("renegade", "smuggle_file", {"path": str(contraband)}, trace1)
        except AuthorityViolation as exc:
            interrupted = True
            verdict("f", f"страж прервал вызов: {exc}")
        assert interrupted, "ренегат не был прерван"
        assert not contraband.exists(), "контрабанда записана на диск!"
        assert not gw1._adapters["renegade"].crimes, "ренегат успел совершить грех"
        kinds1 = types_of(journal, trace1)
        assert "security.violation" in kinds1 and "act" not in kinds1, kinds1
        verdict("g", "сцена 1: ренегат fs:read-only прерван ДО записи; файл не создан; security.violation в крови, act нет (была красная находка №1)")

        # --- сцена 2: ренегат network: none ---
        trace2 = "w7-scene2-net"
        interrupted = False
        try:
            gw1.call("renegade", "phone_home", {}, trace2)
        except AuthorityViolation as exc:
            interrupted = True
            verdict("f", f"страж прервал соединение: {exc}")
        assert interrupted, "сокет не был прерван"
        assert not gw1._adapters["renegade"].crimes, "ренегат успел позвонить домой"
        kinds2 = types_of(journal, trace2)
        assert "security.violation" in kinds2 and "act" not in kinds2, kinds2
        verdict("g", "сцена 2: ренегат network:none прерван до сетевого вызова; security.violation в крови (была красная находка №1, сеть)")

        # --- сцена 3: AuthorityViolation сквозь цикл — G1-полный трейс ---
        trace3 = "w7-scene3-loop"
        loop = Loop(gw1, journal)
        plan = [Step(organ="renegade", tool="smuggle_file", payload={"path": str(contraband)}, intent="записать контрабанду")]
        escaped = False
        result = None
        try:
            result = loop.run(plan, trace_id=trace3)
        except AuthorityViolation:
            escaped = True
        assert not escaped, "AuthorityViolation вылетел из Loop.run"
        assert result is False, f"run() вернул {result!r}, ожидался False"
        kinds3 = types_of(journal, trace3)
        assert kinds3 == ["plan", "security.violation", "reflect", "halt"], kinds3
        assert sum(1 for t in kinds3 if t == "halt") == 1
        verdict("g", f"сцена 3: цикл закрыл трейс без исключения: {' -> '.join(kinds3)} (была красная находка №3)")

        # --- сцена 4: замена при invoke-падении + идентичность привязки ---
        path4 = manifest_file(
            tmp,
            [entry("fallen", "tests.fakes:FakeFallen"), entry("reserve", "tests.fakes:FakeEcho")],
            subs={"fallen": ["reserve"]},
        )
        gw4 = Gateway(path4, journal)
        trace4 = "w7-scene4-replace"
        result = gw4.call("fallen", "echo", {"data": "x"}, trace4)
        assert result is not None, "резерв не ответил"
        kinds4 = types_of(journal, trace4)
        assert "organ.replace" in kinds4 and "error" in kinds4, kinds4
        verdict("g", f"сцена 4а: invoke-падение обслужено резервом: {' -> '.join(kinds4)} (была красная находка №2)")

        impostor_entry = dict(entry("reserve", "tests.fakes:FakeEcho"))
        refused = False
        try:
            gw4.bind_adapter("fallen", FakeEcho(impostor_entry))
        except GatewayConfigError:
            refused = True
        assert refused, "самозванец принят"
        refused2 = False
        try:
            gw4.bind_adapter("fallen", object())
        except GatewayConfigError:
            refused2 = True
        assert refused2, "безымянный принят"
        result2 = gw4.call("fallen", "echo", {"data": "y"}, "w7-scene4-bind")
        assert result2 is not None, "прежняя привязка сломана отказом привязки"
        kinds4b = types_of(journal, "w7-scene4-bind")
        assert "organ.replace" in kinds4b, kinds4b
        verdict("g", "сцена 4б: самозванец и безымянный отклонены до вызова, прежняя (упавшая) привязка жива и обслужена резервом (была красная находка №4)")

        # --- сцена 5: грамматика fail-closed + живой манифест дома ---
        bad_labels = [
            {"fs": "read-only-input-dir", "network": "none", "process": "none"},
            {"fs": "walrus", "network": "none", "process": "none"},
            {"fs": "none", "network": {"hosts": []}, "process": "none"},
        ]
        refused = 0
        for i, authority in enumerate(bad_labels):
            path5 = manifest_file(tmp, [entry("bad", "tests.fakes:FakeEcho", authority=authority)])
            try:
                Gateway(path5)
            except GatewayConfigError:
                refused += 1
        assert refused == len(bad_labels), f"грамматика пропустила неисполнимые ярлыки: {refused}/{len(bad_labels)}"
        verdict("g", "сцена 5а: неисполнимые ярлыки прошлого не дают шлюзу стартовать (fail-closed)")

        home = Gateway(REPO / "synapse" / "mcp-manifest.yaml", journal)
        verdict("g", f"сцена 5б: живой манифест дома стартует на новой грамматике; органы: {', '.join(home.organ_names)}")

        # --- кровь: конверты уже на диске (attach), сверяем счёт и валидность ---
        lines = BLOOD_PATH.read_text(encoding="utf-8").splitlines()
        for line in lines:
            validate(json.loads(line))
        verdict("f", f"кровь: {len(lines)} конвертов, все валидны схемой; трейсы сцен 1..5 в порядке строк")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    red = sum(1 for v in VERDICTS if v.startswith("[КРАСНО]"))
    print()
    print(f"ИТОГ: {len(VERDICTS) - red} зелёных вердиктов, {red} красных")
    return 1 if red else 0


if __name__ == "__main__":
    sys.exit(main())
