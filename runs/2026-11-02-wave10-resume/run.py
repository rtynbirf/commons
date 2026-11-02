"""Живой прогон волны №10: resume из крови (SPEC-0003 v0.5.0, пп.7-8).

Прогон печатает факты, не предсказания. Сцены:
1. цепочка prev_id пишется журналом (первый конверт — без prev_id);
2. подделки ловятся при чтении: удаление, подмена id, вставка;
3. вся пролитая кровь runs/ без гэпов: старая — валидна навсегда без цепочки,
   новая (эта волна) — с целой цепочкой;
4. живая сессия ствола мозга реконструируется по журналу: план, вызовы,
   наблюдения, вердикты, остановки, полная цена — и halt-сессия тоже;
5. гэп в трейсе честно роняет complete, не стирая ткань реконструкции.

Кровь волны пишется тем же журналом, что и сцены 4-5: runs/2026-11-02-wave10-resume/blood.jsonl.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import make  # noqa: E402
from blood.journal import Journal, verify  # noqa: E402
from blood.resume import reconstruct  # noqa: E402
from brainstem import Budget, Loop, Step  # noqa: E402

RUN_DIR = Path(__file__).resolve().parent
BLOOD_PATH = RUN_DIR / "blood.jsonl"

GREEN: list[str] = []
RED: list[str] = []


def verdict(ok: bool, name: str, detail: str) -> None:
    (GREEN if ok else RED).append(f"{name}: {detail}")
    print(f"[ЗЕЛЁНО] {name}: {detail}" if ok else f"[КРАСНО] {name}: {detail}")


# --- сцена 1: цепочка пишется ---------------------------------------------------

def scene_chain() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "blood.jsonl"
        journal = Journal()
        journal.attach(path)
        envelopes = [
            journal.append(make("plan", "brainstem", "self", "t1", {"index": index}))
            for index in range(4)
        ]
        journal.close()

        no_prev_first = "prev_id" not in envelopes[0]
        links_ok = all(
            envelopes[i]["prev_id"] == envelopes[i - 1]["id"] for i in range(1, 4)
        )
        report = verify(path)
        verdict(
            no_prev_first and links_ok and report["gaps"] == [] and report["chained"],
            "1: цепочка prev_id пишется журналом",
            "первый конверт без prev_id, 3 звена сшиты, verify: 0 гэпов, chained=true",
        )


# --- сцена 2: подделки ловятся ---------------------------------------------------

def _chain_file(tmp: str, name: str, count: int = 4) -> Path:
    path = Path(tmp) / name
    journal = Journal()
    journal.attach(path)
    for index in range(count):
        journal.append(make("plan", "brainstem", "self", "t1", {"index": index}))
    journal.close()
    return path


def scene_tampering() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        # 2а: удаление среднего конверта
        removed = _chain_file(tmp, "removed.jsonl")
        lines = removed.read_text(encoding="utf-8").splitlines()
        del lines[1]
        (Path(tmp) / "removed-cut.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        report = verify(Path(tmp) / "removed-cut.jsonl")
        verdict(
            len(report["gaps"]) >= 1 and report["events"] == 3,
            "2а: удаление конверта",
            report["gaps"][0]["reason"] if report["gaps"] else "не пойман",
        )

        # 2б: подмена id первого конверта
        substituted = _chain_file(tmp, "substituted.jsonl")
        lines = substituted.read_text(encoding="utf-8").splitlines()
        forged = json.loads(lines[0])
        forged["id"] = "00000000-0000-4000-8000-000000000000"
        lines[0] = json.dumps(forged, ensure_ascii=False)
        (Path(tmp) / "substituted-cut.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        report = verify(Path(tmp) / "substituted-cut.jsonl")
        verdict(
            len(report["gaps"]) >= 1,
            "2б: подмена id конверта",
            report["gaps"][0]["reason"] if report["gaps"] else "не пойман",
        )

        # 2в: вставка чужого конверта без prev_id
        inserted = _chain_file(tmp, "inserted.jsonl")
        lines = inserted.read_text(encoding="utf-8").splitlines()
        outsider = make("plan", "brainstem", "self", "t1", {"index": 1.5})
        lines.insert(2, json.dumps(outsider, ensure_ascii=False))
        (Path(tmp) / "inserted-cut.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        report = verify(Path(tmp) / "inserted-cut.jsonl")
        caught = next(
            (gap["reason"] for gap in report["gaps"] if "без prev_id" in gap["reason"]),
            None,
        )
        verdict(caught is not None, "2в: вставка конверта без prev_id", caught or "не пойман")


# --- сцена 3: вся пролитая кровь -------------------------------------------------

def scene_poured_blood() -> None:
    journals = sorted(REPO_ROOT.glob("runs/*/blood.jsonl"))
    total_events = 0
    total_gaps = 0
    chained_files = 0
    for journal_path in journals:
        report = verify(journal_path)
        total_events += report["events"]
        total_gaps += len(report["gaps"])
        chained_files += 1 if report["chained"] else 0
    verdict(
        total_gaps == 0 and bool(journals),
        "3: пролитая кровь без гэпов",
        f"файлов {len(journals)}, конвертов {total_events}, гэпов 0; "
        f"цепочка заявлена в {chained_files} (кровь этой волны), "
        f"остальные — валидная кровь v0.4.0 без цепочки",
    )


# --- сцены 4-5: реконструкция сессии ---------------------------------------------

def _manifest(tmp: str) -> Path:
    import yaml

    manifest = {
        "version": "0.2.0",
        "updated": "2026-11-02",
        "transport_default": "stdio",
        "organs": [
            {
                "name": "sense-a",
                "system": "senses",
                "mode": "dependency",
                "upstream": "https://example.invalid/a",
                "license": "MIT",
                "transport": "stdio",
                "command": "fake-a",
                "healthcheck": "initialize handshake",
                "tools": ["echo"],
                "authority": {"fs": "read-only", "network": "none"},
                "adapter": "tests.fakes:FakeEcho",
            }
        ],
        "substitutions": {},
    }
    path = Path(tmp) / "manifest.yaml"
    path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    return path


def scene_reconstruction() -> None:
    from synapse.gateway import Gateway

    with tempfile.TemporaryDirectory() as tmp:
        journal = Journal()
        journal.attach(BLOOD_PATH)
        gateway = Gateway(_manifest(tmp), journal)
        loop = Loop(gateway, journal)

        # живая завершённая сессия: два намерения, оба удовлетворены
        completed_plan = [
            Step(organ="sense-a", tool="echo", payload={"n": 1}, intent="первое намерение"),
            Step(organ="sense-a", tool="echo", payload={"n": 2}, intent="второе намерение"),
        ]
        assert loop.run(completed_plan) is True
        completed_trace = journal.by_type("plan")[0]["trace_id"]

        # остановленная сессия: бюджет в 1 токен исчерпан первым вызовом
        halted_plan = [
            Step(organ="sense-a", tool="echo", payload={"n": 1}, intent="успеть до исчерпания"),
            Step(organ="sense-a", tool="echo", payload={"n": 2}, intent="уже не случится"),
        ]
        assert loop.run(halted_plan, budget=Budget(tokens_in=1)) is False
        halted_trace = journal.by_type("plan")[-1]["trace_id"]
        journal.close()

        session = reconstruct(BLOOD_PATH, completed_trace)
        plan_ok = [entry["intent"] for entry in session["plan"]] == [
            "первое намерение",
            "второе намерение",
        ]
        tissue_ok = (
            len(session["acts"]) == 2
            and len(session["observes"]) == 2
            and len(session["reflects"]) == 2
            and all(entry["satisfied"] is True for entry in session["reflects"])
            and session["halts"] == []
        )
        price_ok = (
            session["totals"]["tokens_in"] == journal.totals(completed_trace).tokens_in
            and session["totals"]["tokens_out"] == journal.totals(completed_trace).tokens_out
            and session["totals"]["seconds"] == journal.totals(completed_trace).seconds
        )
        verdict(
            session["complete"] is True and session["gaps"] == [] and plan_ok and tissue_ok and price_ok,
            "4а: живая сессия реконструируется целиком",
            f"trace {completed_trace}: план 2/2, акты 2, рефлексии удовлетворены, "
            f"цена {session['totals']['tokens_in']}/{session['totals']['tokens_out']} "
            f"токенов, {session['totals']['seconds']:.2f} c — совпадает с кровью",
        )

        halt_session = reconstruct(BLOOD_PATH, halted_trace)
        halt_ok = (
            halt_session["complete"] is True
            and len(halt_session["halts"]) == 1
            and "бюджет исчерпан" in halt_session["halts"][0]["reason"]
            and halt_session["halts"][0]["at_step"] == 1
            and len(halt_session["plan"]) == 1
            and halt_session["totals"]["tokens_in"] == journal.totals(halted_trace).tokens_in
        )
        verdict(
            halt_ok,
            "4б: halt-сессия реконструируется с причиной и шагом",
            f"trace {halted_trace}: {halt_session['halts'][0]['reason']!r} на шаге "
            f"{halt_session['halts'][0]['at_step']}, complete=true",
        )

        # сцена 5: гэп в трейсе роняет complete, ткань остаётся
        with tempfile.TemporaryDirectory() as tamper_tmp:
            tampered = Path(tamper_tmp) / "tampered.jsonl"
            shutil.copy(BLOOD_PATH, tampered)
            lines = tampered.read_text(encoding="utf-8").splitlines()
            forged = json.loads(lines[1])  # act завершённой сессии
            forged["prev_id"] = "11111111-1111-4111-8111-111111111111"
            lines[1] = json.dumps(forged, ensure_ascii=False)
            tampered.write_text("\n".join(lines) + "\n", encoding="utf-8")

            session = reconstruct(tampered, completed_trace)
            verdict(
                bool(session["gaps"]) and session["complete"] is False and bool(session["plan"]),
                "5: гэп роняет complete, ткань трейса не стирается",
                f"гэпов {len(session['gaps'])}, complete=false, "
                f"план из {len(session['plan'])} намерений восстановлен",
            )


def main() -> int:
    print(f"=== волна №10: resume из крови (SPEC-0003 v0.5.0) ===")
    scene_chain()
    scene_tampering()
    scene_reconstruction()
    scene_poured_blood()
    print()
    print(f"ИТОГ: {len(GREEN)} зелёных вердиктов, {len(RED)} красных")
    if RED:
        for line in RED:
            print(f"  КРАСНО: {line}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
