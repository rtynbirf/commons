# Живой прогон волны №27 (0.46.0): забывание памяти (Ф-1.4/PR-4, A11,
# SPEC-0005 п.7) и обмен памятью с провенансом (A12/A13, ASI06 Ф-2.6,
# SPEC-0005 п.8). Сцены: живая память DefaultMemory — забыл событие и трейс
# (кровь не тронута), не нашёл — честный NOT_FOUND, экспорт снапшота с
# провенансом, импорт в свежий дом с roundtrip-поиском, ядовитые снапшоты
# отвергнуты fail-closed, ручная правка названа конфликтом, память без
# счётчиков — честный OUT_OF_CONTROL. Кровь проливает сам дом — органов
# в прогоне нет (забывает производную память, не организм).
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, seal, verify  # noqa: E402
from memory.engine import DefaultMemory  # noqa: E402
from memory.forget import forget  # noqa: E402
from memory.graph import MemoryGraph  # noqa: E402
from memory.trade import export, import_snapshot  # noqa: E402

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
SNAPSHOT = HERE / "snapshot.json"
TRACE = "wave27-forget-trade"

journal = Journal()
journal.attach(JOURNAL)

journal.append(make(
    event_type="boot",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "role": "волна №27 (0.46.0): забывание памяти (Ф-1.4/PR-4, A11, SPEC-0005 п.7) + обмен памятью с провенансом (A12/A13, ASI06, п.8)",
        "directive": "забыть — только с честным отчётом по каждому хранилищу; кровь не трогается никогда",
        "honesty": "органов в прогоне нет — забывает производная память; файлы движков — во временном каталоге, снапшот-доказательство остаётся в прогоне",
    },
    cost=Cost(),
))


def _smoke(step: int, scene: str, result: str) -> None:
    journal.append(make(
        event_type="observe",
        source="brainstem",
        organ="self",
        trace_id=TRACE,
        payload={"step": step, "scene": scene, "result": result},
        cost=Cost(),
    ))


_workdir = Path(tempfile.mkdtemp(prefix="wave27-live-"))

# --- Сцена 1: живая память — забыл одно событие; кровь не тронута ---------------
mem = DefaultMemory(_workdir / "home")
e1 = make("reflect", "brainstem", "echo-a", f"{TRACE}-сцена1", {"what": "помнить и забыть"}, Cost())
mem.observe(e1)
assert mem.index.count() == 1
r1 = forget(mem, event_id=e1["id"])
assert r1["index"]["status"] == "DELETED" and mem.index.count() == 0
assert r1["blood"]["status"] == "OUT_OF_CONTROL" and "append-only" in r1["blood"]["reason"]
assert r1["graph"]["status"] == "OUT_OF_CONTROL", "граф хранит обмены, не события — граница названа"
_smoke(1, "забыл одно событие (event_id)",
       f"index DELETED, граф OUT_OF_CONTROL (обмены, не события), кровь OUT_OF_CONTROL (append-only) — граница названа")

# --- Сцена 2: забыл трейс с подтрейсами — индекс и граф точно --------------------
mem2 = DefaultMemory(_workdir / "home2")
for i in range(3):
    mem2.observe(make("reflect", "brainstem", "echo-a", f"{TRACE}-сцена2-{i}", {"шаг": i}, Cost()))
mem2.observe(make("reflect", "brainstem", "echo-a", f"{TRACE}-сцена2-0-стык", {"стык": True}, Cost()))
assert mem2.index.count() == 4
r2 = forget(mem2, trace_id=f"{TRACE}-сцена2")
assert r2["index"]["status"] == "DELETED" and r2["index"]["removed"] == 4, r2
assert r2["graph"]["status"] == "DELETED" and r2["graph"]["exact"] is True, r2
assert r2["graph"]["envelopes"] == 4, r2
assert mem2.index.count() == 0
_smoke(2, "забыл трейс с подтрейсами `<trace>-*`",
       f"index DELETED ({r2['index']['removed']} записи), граф DELETED exact (конвертов {r2['graph']['envelopes']}, рёбер снято {r2['graph']['removed_edges']}, узлов {r2['graph']['removed_nodes']})")

# --- Сцена 3: забыл то, чего не было — честный NOT_FOUND -------------------------
r3 = forget(mem2, event_id="нет-такого")
assert r3["status"] == "NOT_FOUND", r3
r3b = forget(mem2, trace_id="нет-такого-трейса")
assert r3b["index"]["status"] == "NOT_FOUND" and r3b["graph"]["status"] == "NOT_FOUND", r3b
_smoke(3, "не нашёл — честный NOT_FOUND",
       "события не было; трейса не было (счётчики графа говорят точно) — выдумывать нечего")

# --- Сцена 4: экспорт снапшота с провенансом -------------------------------------
mem3 = DefaultMemory(_workdir / "home3")
for i in range(3):
    mem3.observe(make("reflect", "brainstem", "markitdown", f"{TRACE}-сцена4-{i}", {"знание": f"выжимка {i}"}, Cost()))
exp = export(mem3, SNAPSHOT)
assert exp["status"] == "EXPORTED" and exp["items"] == 3, exp
data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
assert data["schema"] == "commons-memory/v1"
assert all(item["meta"]["provenance"]["origin"] == "blood" for item in data["items"])
_smoke(4, "экспорт снапшота commons-memory/v1",
       f"записей {exp['items']}, у каждой провенанс origin=blood + event_id — снапшот говорит, откуда что взялось")

# --- Сцена 5: импорт в свежий дом — roundtrip восстанавливает поиск --------------
fresh = DefaultMemory(_workdir / "fresh")
diff = import_snapshot(fresh, SNAPSHOT)
assert diff["added"] == 3 and diff["rejected"] == [] and diff["conflicts"] == [], diff
hits = fresh.context("выжимка 2", k=1)
assert hits, "после импорта память ищется (A13)"
again = import_snapshot(fresh, SNAPSHOT)
assert again["added"] == 0 and again["skipped"] == 3, again
_smoke(5, "импорт в свежий дом + повторный импорт",
       f"added {diff['added']}, поиск находит (A13); повторный импорт: added 0, skipped {again['skipped']} — эффект не повторяется")

# --- Сцена 6: ядовитые снапшоты не входят молча (ASI06) --------------------------
poisoned = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
for item in poisoned["items"]:
    del item["meta"]["provenance"]
poisoned_path = _workdir / "no-provenance.json"
poisoned_path.write_text(json.dumps(poisoned, ensure_ascii=False), encoding="utf-8")
d6a = import_snapshot(DefaultMemory(_workdir / "fresh6a"), poisoned_path)
assert d6a["added"] == 0 and len(d6a["rejected"]) == 3, d6a

foreign = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
for item in foreign["items"]:
    item["meta"]["provenance"]["origin"] = "слышал в интернете"
foreign_path = _workdir / "foreign-origin.json"
foreign_path.write_text(json.dumps(foreign, ensure_ascii=False), encoding="utf-8")
d6b = import_snapshot(DefaultMemory(_workdir / "fresh6b"), foreign_path)
assert d6b["added"] == 0 and len(d6b["rejected"]) == 3, d6b

alien = _workdir / "alien.json"
alien.write_text(json.dumps({"schema": "чужой-формат", "items": []}, ensure_ascii=False), encoding="utf-8")
d6c = import_snapshot(DefaultMemory(_workdir / "fresh6c"), alien)
assert d6c["added"] == 0 and d6c["rejected"] and "схемы" in d6c["rejected"][0]["reason"], d6c
_smoke(6, "ядовитые снапшоты fail-closed (ASI06)",
       f"без провенанса: rejected {len(d6a['rejected'])}; чужое слово происхождения: rejected {len(d6b['rejected'])}; чужая схема: rejected {len(d6c['rejected'])} — ни одна не вошла молча")

# --- Сцена 7: ручная правка названа конфликтом (A12) -----------------------------
edited = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
edited["items"][0]["vector"] = [1.0 if x == 0 else x for x in edited["items"][0]["vector"]]
edited_path = _workdir / "edited.json"
edited_path.write_text(json.dumps(edited, ensure_ascii=False), encoding="utf-8")
d7 = import_snapshot(fresh, edited_path)
assert d7["added"] == 0 and d7["conflicts"], d7
_smoke(7, "ручная правка памяти — конфликт назван (A12)",
       f"конфликтов {len(d7['conflicts'])}, записей не перезаписано молча")

# --- Сцена 8: память без счётчиков — честный OUT_OF_CONTROL ----------------------
g8 = MemoryGraph()
g8.add_envelope(make("reflect", "brainstem", "echo-a", f"{TRACE}-сцена8", {"старая": "память"}, Cost()))
g8._trace_counts = {}  # память, написанная до волны №27
r8 = g8.forget_trace(f"{TRACE}-сцена8")
assert r8["exact"] is False and r8["status"] == "OUT_OF_CONTROL", r8
_smoke(8, "память до волны №27 — OUT_OF_CONTROL, не имитация",
       "счётчиков нет — точное забывание невозможно; G1: перестроить из крови можно, «забыть точнее крови» — нельзя")

shutil.rmtree(_workdir, ignore_errors=True)  # файлы движков — во временно́м каталоге; снапшот-доказательство остаётся

# --- Печать и сверка своей крови ------------------------------------------------
anchor = seal(JOURNAL)
report_verify = verify(JOURNAL, anchor=anchor)
assert report_verify["gaps"] == [] and report_verify["content_gaps"] == [] and report_verify["skipped"] == 0, report_verify
envelopes = journal.by_trace(TRACE)
print(f"WAVE27: {len(envelopes)} конвертов, 0 гэпов, chained + hashed, опечатана якорем; "
      f"сцен 8, снапшот {exp['items']} записей с провенансом")
