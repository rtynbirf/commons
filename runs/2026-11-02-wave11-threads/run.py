"""Живой прогон волны №11: страж и потоки (SPEC-0002 v0.6.0, п.8).

Прогон печатает факты, не предсказания. Сцены:
1. escape через threading закрыт: поток, рождённый под стражем, наследует его —
   запись при fs: read-only прервана, файла нет;
2. шлюз: ренегат-в-потоке отдаёт security.violation в кровь, не act;
3. внук (поток в потоке-наследнике) и подкласс Thread тоже под стражем;
4. граница действия: поток, рождённый вне вызова, стража не имеет — жив;
5. пул с ленивым стартом внутри вызова наследует стража;
6. запись `__pycache__` прервана, текст нарушения называет предписание;
7. кровь волны: цепочка prev_id цела — verify: 0 гэпов, chained=true.

Кровь волны пишется тем же журналом: runs/2026-11-02-wave11-threads/blood.jsonl.
"""

from __future__ import annotations

import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import yaml  # noqa: E402

from blood.envelope import make  # noqa: E402
from blood.journal import Journal, verify  # noqa: E402
from synapse.authority import AuthorityViolation, enforce  # noqa: E402
from synapse.gateway import Gateway  # noqa: E402

RUN_DIR = Path(__file__).resolve().parent
BLOOD_PATH = RUN_DIR / "blood.jsonl"

GREEN: list[str] = []
RED: list[str] = []

BLOOD_JOURNAL = Journal()
BLOOD_JOURNAL.attach(BLOOD_PATH)
TRACE = "wave11-threads"


def verdict(ok: bool, name: str, detail: str) -> None:
    (GREEN if ok else RED).append(f"{name}: {detail}")
    kind = "reflect" if ok else "error"
    BLOOD_JOURNAL.append(
        make(
            kind,
            "wave11",
            "self",
            TRACE,
            {"scene": name, "detail": detail, "verdict": "green" if ok else "red"},
        )
    )
    print(f"[ЗЕЛЁНО] {name}: {detail}" if ok else f"[КРАСНО] {name}: {detail}")


def scene_plan(name: str, index: int) -> None:
    BLOOD_JOURNAL.append(
        make("plan", "wave11", "self", TRACE, {"scene": name, "index": index})
    )


# --- сцена 1: escape через threading закрыт -------------------------------------

def scene_escape() -> None:
    scene_plan("escape-closed", 1)
    caught: list[BaseException] = []
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "smuggled.txt"

        with enforce({"fs": "read-only", "network": "none", "process": "none"}, organ="wave11-renegade"):
            def crime() -> None:
                try:
                    with open(target, "w", encoding="utf-8") as fh:
                        fh.write("контрабанда из потока")
                except BaseException as exc:  # честный поток: нарушение не глотается
                    caught.append(exc)

            worker = threading.Thread(target=crime, name="wave11-escape")
            worker.start()
            worker.join(timeout=5)

        violation = bool(caught) and isinstance(caught[0], AuthorityViolation)
        verdict(
            violation and not target.exists(),
            "1: escape через threading закрыт",
            "поток под стражем наследует его: AuthorityViolation в потоке, "
            f"файл не записан ({'нарушение поймано' if violation else 'СТРАЖ НЕ АКТИВЕН'})",
        )


# --- сцена 2: шлюз — ренегат-в-потоке в крови ------------------------------------

def _manifest(tmp: str) -> Path:
    manifest = {
        "version": "0.2.0",
        "updated": "2026-11-02",
        "transport_default": "stdio",
        "organs": [
            {
                "name": "threaded",
                "system": "senses",
                "mode": "dependency",
                "upstream": "https://example.invalid/threaded",
                "license": "MIT",
                "transport": "stdio",
                "command": "fake-threaded",
                "healthcheck": "initialize handshake",
                "tools": ["smuggle_in_thread"],
                "authority": {"fs": "read-only", "network": "none", "process": "none"},
                "adapter": "tests.fakes:FakeThreadedRenegade",
            }
        ],
        "substitutions": {},
    }
    path = Path(tmp) / "manifest.yaml"
    path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    return path


def scene_gateway() -> None:
    scene_plan("gateway-blood", 2)
    with tempfile.TemporaryDirectory() as tmp:
        journal = Journal()
        gateway = Gateway(_manifest(tmp), journal)
        raised = False
        try:
            gateway.call("threaded", "smuggle_in_thread", {"path": str(Path(tmp) / "x.txt")}, TRACE)
        except AuthorityViolation:
            raised = True
        violations = journal.by_type("security.violation")
        verdict(
            raised and len(violations) == 1 and not journal.by_type("act"),
            "2: ренегат-в-потоке отдаёт security.violation в кровь",
            f"invoke поднял AuthorityViolation={raised}, security.violation в крови: "
            f"{len(violations)}, act: {len(journal.by_type('act'))} (нарушенный вызов не act)",
        )
        journal.close()


# --- сцена 3: внук и подкласс ----------------------------------------------------

def scene_nested() -> None:
    scene_plan("nested-and-subclass", 3)
    caught: list[BaseException] = []
    subclass_caught: list[BaseException] = []

    with tempfile.TemporaryDirectory() as tmp:
        with enforce({"fs": "read-only", "network": "none", "process": "none"}, organ="wave11-grandpa"):

            def child() -> None:
                def crime() -> None:
                    try:
                        with open(Path(tmp) / "grandchild.txt", "w", encoding="utf-8") as fh:
                            fh.write("контрабанда внука")
                    except BaseException as exc:
                        caught.append(exc)

                worker = threading.Thread(target=crime, name="wave11-grandchild")
                worker.start()
                worker.join(timeout=5)

            middle = threading.Thread(target=child, name="wave11-child")
            middle.start()
            middle.join(timeout=5)

            target = Path(tmp) / "subclass.txt"

            class RealCriminal(threading.Thread):
                def run(self) -> None:
                    try:
                        with open(target, "w", encoding="utf-8") as fh:
                            fh.write("контрабанда подкласса")
                    except BaseException as exc:
                        subclass_caught.append(exc)

            criminal = RealCriminal(name="wave11-subclass")
            criminal.start()
            criminal.join(timeout=5)

        grand = any(isinstance(e, AuthorityViolation) for e in caught)
        sub = any(isinstance(e, AuthorityViolation) for e in subclass_caught)
        verdict(
            grand and sub,
            "3: внук и подкласс Thread под стражем",
            f"внук: AuthorityViolation={grand}, подкласс (run без target): AuthorityViolation={sub}",
        )


# --- сцена 4: граница действия ----------------------------------------------------

def scene_boundary() -> None:
    scene_plan("boundary", 4)
    done = threading.Event()
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "outside.txt"

        def honest_work() -> None:
            with open(target, "w", encoding="utf-8") as fh:
                fh.write("не орган: обычный код процесса")
            done.set()

        worker = threading.Thread(target=honest_work, name="wave11-outside")
        worker.start()
        worker.join(timeout=5)
        verdict(
            done.is_set() and target.exists(),
            "4: граница действия — поток вне вызова жив",
            "поток, рождённый вне enforce, стража не имеет (граница задокументирована в п.8): файл записан",
        )


# --- сцена 5: пул с ленивым стартом ----------------------------------------------

def scene_pool() -> None:
    scene_plan("pool-lazy-start", 5)
    caught: list[BaseException] = []
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "pool.txt"

        with enforce({"fs": "read-only", "network": "none", "process": "none"}, organ="wave11-pool"):
            with ThreadPoolExecutor(max_workers=1) as pool:  # рабочие стартуют на submit — под стражем
                pool.submit(_try_write, target, caught).result(timeout=5)

        violation = any(isinstance(e, AuthorityViolation) for e in caught)
        verdict(
            violation and not target.exists(),
            "5: пул с ленивым стартом внутри вызова под стражем",
            "рабочий поток стартовал при первом submit под стражем — запись прервана",
        )


def _try_write(target: Path, caught: list[BaseException]) -> None:
    try:
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("контрабанда из пула")
    except BaseException as exc:
        caught.append(exc)


# --- сцена 6: pycache-предписание -------------------------------------------------

def scene_pycache() -> None:
    scene_plan("pycache-prescription", 6)
    with tempfile.TemporaryDirectory() as tmp:
        pycache = Path(tmp) / "__pycache__" / "organ_lazy.pyc"
        pycache.parent.mkdir()
        text = ""
        with enforce({"fs": "read-only", "network": "none", "process": "none"}, organ="wave11-lazy"):
            try:
                with open(pycache, "wb") as fh:  # имитация ленивого импорта внутри invoke
                    fh.write(b"\x00bytecode")
            except AuthorityViolation as exc:
                text = str(exc)
        verdict(
            "прогрейте импорты" in text and not pycache.exists(),
            "6: __pycache__ — нарушение с предписанием",
            f"текст называет средство: «...{text[-70:]}»" if text else "нарушения не было",
        )


# --- сцена 7: кровь волны ---------------------------------------------------------

def scene_blood() -> None:
    scene_plan("wave-blood", 7)
    BLOOD_JOURNAL.append(
        make("halt" if RED else "shutdown", "wave11", "self", TRACE, {"verdicts": len(GREEN), "red": len(RED)})
    )
    BLOOD_JOURNAL.close()
    report = verify(BLOOD_PATH)
    verdict(
        report["gaps"] == [] and report["chained"],
        "7: кровь волны цела",
        f"{report['events']} конвертов, гэпов {len(report['gaps'])}, chained={report['chained']}",
    )
    print(f"\nИТОГ: {len(GREEN)} зелёных / {len(RED)} красных")
    if RED:
        for line in RED:
            print(f"  КРАСНО: {line}")
        sys.exit(1)


def main() -> None:
    scene_escape()
    scene_gateway()
    scene_nested()
    scene_boundary()
    scene_pool()
    scene_pycache()
    scene_blood()


if __name__ == "__main__":
    main()
