# Живой прогон стыка волн №24–№27 (0.48.2) — контрольный забег третьим путём.
# Дисциплина стыков (волны №18/№23): их база принята, наше зерно вжито аддитивно.
# Сцены: их контур одобрения (вопрос P0) живёт в сшитом доме; наш движковый слой
# памяти (забывание по трейсу, снапшот-провенанс) поверх их файлового слоя;
# их dispatcher-кровь под нашим нюхом и проекцией пути; кровь стыка опечатана якорем.
# Урок прогона: каталог прогона не выметается самим прогоном (первый запуск
# удалил собственный скрипт — косяк назван и починен, чистится только кровь).
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import Cost, make  # noqa: E402
from blood.journal import Journal, seal  # noqa: E402
from blood.olfactory import smell  # noqa: E402
from blood.path import path_of  # noqa: E402
from brainstem import Budget, Loop, Step  # noqa: E402
from brainstem.silence import ANSWER_APPROVED, ApprovalRequest, await_approval  # noqa: E402
from memory.engine import DefaultMemory  # noqa: E402
from memory.forget import forget  # noqa: E402
from memory.files import MemoryFiles  # noqa: E402
from memory.trade import export as trade_export  # noqa: E402
from memory.trade import import_snapshot  # noqa: E402

HERE = Path(__file__).resolve().parent
JOURNAL = HERE / "blood.jsonl"
TRACE = "wave30-junction"

HERE.mkdir(parents=True, exist_ok=True)
if JOURNAL.exists():
    JOURNAL.unlink()

journal = Journal()
journal.attach(JOURNAL)

lines: list[str] = []


def note(s: str) -> None:
    lines.append(s)
    print(s)


def scene(step: int, name: str, result: str) -> None:
    journal.append(make(
        event_type="observe",
        source="brainstem",
        organ="self",
        trace_id=TRACE,
        payload={"step": step, "scene": name, "result": result},
        cost=Cost(),
    ))
    note(f"сцена {step}: {name} — {result}")


journal.append(make(
    event_type="boot",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={
        "role": "стык волн №24–№27 (0.48.2): их база принята, наше зерно вжито — контрольный забег третьим путём",
        "honesty": "орган-эхо — подставка, названная в boot (настоящий орган подключает манифест, G5); каналы одобрения — подставки",
    },
    cost=Cost(),
))

note(f"# Стык 0.48.2 ({datetime.now(timezone.utc).isoformat(timespec='seconds')})")

# --- сцена 1: их контур одобрения в сшитом доме — вопрос P0 несёт цену ---
class EchoGateway:
    """Орган-эхо — подставка, названная в boot (G5): зовётся, платит кровью."""

    def __init__(self) -> None:
        self.calls = 0

    def call(self, organ, tool, payload, trace_id, *, reversibility=None, idempotency_key=None):
        self.calls += 1
        journal.append(make(
            "act", "brainstem", "echo", trace_id,
            {"tool": tool, **payload},
            Cost(tokens_in=3, tokens_out=2, seconds=0.01),
        ))
        return {"ok": True, "echo": payload}


echo_gateway = EchoGateway()
T1 = TRACE + "-their-approval"
loop = Loop(echo_gateway, journal, approval_channel=lambda q: ANSWER_APPROVED)
done = loop.run(
    [Step(organ="echo", tool="echo", payload={"k": "v"}, intent="их контур одобрения",
          reversibility="irreversible", approval_window=0.5)],
    trace_id=T1,
    budget=Budget(),
)
asks = [e for e in journal.by_type("approval.requested") if e["trace_id"] == T1]
assert done is True, "их контур одобрения должен довести необратимый шаг до акта"
assert len(asks) == 1 and asks[0]["cost"]["attention"] == 1 and asks[0]["attention_class"] == "P0"
scene(1, "их контур одобрения (окно → granted → акт)",
      f"вопросов=1, внимание_вопроса=1 (P0), актов={len(journal.by_type('act'))}")

# --- сцена 2: наш движковый слой поверх их файлового — один дом, два слоя памяти ---
workdir = Path(tempfile.mkdtemp(prefix="junction-0482-mem-"))
memory = DefaultMemory(workdir)
from memory.replay import replay  # noqa: E402

replay_result = replay(JOURNAL, index=memory.index, graph=memory.graph)
# их слой: файловый экспорт того, что помнит память (кровь — истина)
files = MemoryFiles(index=memory.index, graph=memory.graph, journal=journal, export_dir=HERE / "commons-memory")
exported = files.export()
# наш слой: снапшот-провенанс той же памяти
snapshot = HERE / "snapshot.json"
traded = trade_export(memory, snapshot)
# их forget: трейс выметен из индекса, графа и файлов; кровь — OUT_OF_CONTROL
act_id = next(iter(journal.by_type("act")))["id"]
report = files.forget(act_id, reason="стык: проверка их забвения", by="brainstem")
assert report["blood"] == "OUT_OF_CONTROL", "кровь — вне управления забвения (SPEC-0003)"
# наш forget: трейс с подтрейсами, отчёт по хранилищам
report2 = forget(memory, trace_id=T1)
assert report2["blood"]["status"] == "OUT_OF_CONTROL"
diff = files.diff()
scene(2, "два слоя памяти в одном доме",
      f"replay событий={len(journal.all())}; их_экспорт={exported['records']} записей; наш_снапшот={traded['items']} записей; "
      f"их_забвение={report['index']}; наше_забывание_трейса={report2['status']}; "
      f"diff после забвения: только_в_файлах={len(diff['only_in_files'])}")
# восстановление из бэкапа (A13 roundtrip): снапшот вернул запись в живую память
restore = import_snapshot(memory, snapshot)
assert restore["added"] == 1, "roundtrip: снапшот восстанавливает запись"
# повторная доставка — эффект не повторяется (A01)
again = import_snapshot(memory, snapshot)
assert again["added"] == 0 and again["skipped"] == 1, "повторный импорт того же снапшота — без эффекта (A01)"
# G4: забытое по надгробию не оживает даже из снапшота-бэкапа
reflect_id = next(iter(journal.by_type("reflect")))["id"]
files.forget(reflect_id, reason="стык: надгробие на reflect-записи", by="brainstem")
journal.append(make("observe", "brainstem", "self", TRACE, {"note": "надгробие поставлено их файловым слоем"}, Cost()))
memory.index.delete(reflect_id)  # движок выметен нашим слоем; надгробие — постоянная часть истины
tombstones = {
    e["payload"]["forget"]
    for e in journal.all()
    if e.get("type") == "forget" and isinstance(e.get("payload"), dict) and isinstance(e["payload"].get("forget"), str)
}
g4 = import_snapshot(memory, snapshot, tombstoned=tombstones)
assert g4["added"] == 0 and reflect_id in (g4["skipped_tombstoned"] or []), "надгробие держит: забытое не оживает из бэкапа (G4)"
scene(3, "снапшот-обмен и надгробия",
      f"restore added=1 (A13 roundtrip); повтор added=0, skipped=1 (A01); надгробий в крови={len(tombstones)}, "
      f"пропущено_по_надгробиям={len(g4['skipped_tombstoned'])} (G4: забытое не оживает из бэкапа)")
shutil.rmtree(workdir, ignore_errors=True)

# --- сцена 4: вся кровь стыка под нашим нюхом и проекцией пути ---
smells = smell(JOURNAL)
all_events = [json.loads(l) for l in JOURNAL.read_text(encoding="utf-8").splitlines() if l.strip()]
t1_events = [e for e in all_events if e.get("trace_id") == T1]
path_report = path_of(t1_events)
scene(4, "нюх крови + проекция пути (наше зерно поверх их крови)",
      f"запахов={len(smells)} ({'; '.join(smells[:2])}); путь одобрительного трейса: "
      f"планов={path_report['plans']}, актов={path_report['acts']}, вопросов={path_report['interruptions']}, "
      f"исход={path_report['outcome']}")


journal.append(make(
    event_type="shutdown",
    source="brainstem",
    organ="self",
    trace_id=TRACE,
    payload={"scenes": 4, "verdict": "стык жив: обе линии служат в одном доме, кровь опечатана"},
    cost=Cost(),
))
SHUT = True  # печать — строго после последнего события крови

# --- печать крови стыка якорем (W-0026) — строго после последнего события,
# протухшие строки этого прогона выметаются (урок их волны №27: в доме одна
# печать, сходящаяся с живой кровью) ---
rel = "runs/2026-11-03-wave30-junction/blood.jsonl"
anchor = seal(JOURNAL, name=rel)
anchors_path = REPO_ROOT / "blood" / "anchors.jsonl"
kept = [l for l in anchors_path.read_text(encoding="utf-8").splitlines()
        if l.strip() and json.loads(l).get("file") != rel]
kept.append(json.dumps(anchor, ensure_ascii=False))
anchors_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
note(f"печать стыка: событий={anchor['events']}, якорь last_id={anchor['last_id'][:8]}…, chained+hashed")

from blood.diary import render  # noqa: E402

(HERE / "output.md").write_text(
    "# Дневник стыка 0.48.2 — кровь волн №24–№27 в человеческом языке\n\n" + render(JOURNAL),
    encoding="utf-8",
)

report_md = ["# Отчёт живого прогона стыка (0.48.2)\n"]
report_md += [l + "\n" for l in lines]
report_md += ["\nКровь: runs/2026-11-03-wave30-junction/blood.jsonl — chained+hashed, опечатана якорем.\n",
              "Приёмки стыка: tests/test_wave30_junction.py.\n"]
(HERE / "report.md").write_text("\n".join(report_md), encoding="utf-8")
print("OK")
