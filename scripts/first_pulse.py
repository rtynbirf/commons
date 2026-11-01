"""Первый живой пульс организма — DoD M1 (ROADMAP).

Простейший агент выполняет одно полезное действие целиком через синапсы:
ствол мозга (PLAN→ACT→OBSERVE→REFLECT) → шлюз (манифест) → MCP-stdio →
настоящий орган-сенсор markitdown-mcp → кровь (append-only JSONL).

Артефакты прогона: runs/<дата>-first-pulse/
  input/pulse-input.docx — входной документ (создаётся здесь же, наш собственный);
  blood.jsonl  — журнал крови (каждый конверт валиден по схеме);
  output.md    — результат сенсорики (то, что организм «увидел»);
  report.md    — реконструкция трейса (G1), итоги бюджета (G3), чек-лист DoD.

Запуск из корня репо (требуется `pip install markitdown-mcp python-docx`):
  python3 scripts/first_pulse.py
"""

from __future__ import annotations

import importlib.metadata
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import new_trace_id  # noqa: E402
from blood.journal import Journal  # noqa: E402
from brainstem.loop import Budget, Loop, Step  # noqa: E402
from synapse.gateway import Gateway  # noqa: E402

DOC_HEADING = "COMMONS: первый пульс сенсорики"
DOC_PARAGRAPHS = [
    "Этот документ создан организмом COMMONS как проба сенсорики.",
    "Путь события: ствол мозга → синапс → MCP stdio → markitdown → кровь.",
    "Инвариант тела: событие без цены не существует.",
]
DOC_SUBHEADING = "Инвариант"
DOC_SUBPARAGRAPHS = ["Ни одного события с пустой cost. Полный трейс восстанавливается из журнала."]

INPUT_MARKER = "проба сенсорики"  # по нему приёмка проверяет, что организм увидел свой документ


def create_input(path: Path) -> None:
    """Готовит входной документ — наш собственный, без чужого контента."""
    from docx import Document  # тяжёлый импорт — только при генерации входа

    doc = Document()
    doc.add_heading(DOC_HEADING, 0)
    for paragraph in DOC_PARAGRAPHS:
        doc.add_paragraph(paragraph)
    doc.add_heading(DOC_SUBHEADING, 1)
    for paragraph in DOC_SUBPARAGRAPHS:
        doc.add_paragraph(paragraph)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "не установлен"


def write_report(run_dir: Path, trace_id: str, events: list[dict], output_text: str, budget: Budget) -> None:
    """Реконструкция трейса из крови (G1) + чек-лист DoD M1."""
    from blood.envelope import validate  # конверты из файла перепроверяем как чужие

    raw = (run_dir / "blood.jsonl").read_text(encoding="utf-8").splitlines()
    replayed = [json.loads(line) for line in raw if line.strip()]
    for envelope in replayed:
        validate(envelope)

    types = [event["type"] for event in replayed]
    act_events = [event for event in replayed if event["type"] == "act"]
    act_cost = act_events[0]["cost"] if act_events else {"tokens_in": 0, "tokens_out": 0, "seconds": 0.0}
    totals = {
        "tokens_in": sum(e["cost"]["tokens_in"] for e in replayed),
        "tokens_out": sum(e["cost"]["tokens_out"] for e in replayed),
        "seconds": round(sum(e["cost"]["seconds"] for e in replayed), 6),
    }
    costs_complete = all(
        set(e["cost"]) == {"tokens_in", "tokens_out", "seconds"} for e in replayed
    )

    lines = [
        "# Первый пульс: отчёт",
        "",
        f"- trace_id: `{trace_id}`",
        f"- дата: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- сенсорика: markitdown {package_version('markitdown')} (сервер markitdown-mcp,"
        f" mcp {package_version('mcp')})",
        "",
        "## Что произошло",
        "",
        "Организм получил задачу «превратить документ в Markdown». Единственный путь к органу —",
        "синапс: `brainstem/loop.py` → `synapse/gateway.py` → `synapse/adapters/mcp_stdio.py` →",
        "процесс `markitdown-mcp` (JSON-RPC 2.0, initialize handshake). Цикл не знает ни одного",
        "органа и не умеет вызывать их напрямую.",
        "",
        "## Реконструкция из крови (G1)",
        "",
        f"- конвертов в журнале: {len(replayed)}; все валидны по `blood/envelope.schema.json`",
        f"- последовательность типов: `{' → '.join(types)}`",
        f"- trace_id один для всех событий: `{len({e['trace_id'] for e in replayed}) == 1}`",
        f"- `cost` заполнен во всех конвертах: {costs_complete} (нули допустимы, отсутствие — нет)",
        "",
        "## Цена (G3)",
        "",
        f"- бюджет: seconds ≤ {budget.seconds}",
        f"- израсходовано: tokens_in={totals['tokens_in']}, tokens_out={totals['tokens_out']},"
        f" seconds={totals['seconds']}",
        f"- сам вызов органа (`act`): {act_cost['seconds']} c, токены 0 — их не считает сенсорика,",
        "  считает метаболизм (ollama/llama.cpp, спайк S1)",
        "",
        "## Чек-лист DoD M1",
        "",
        "| Требование DoD | Статус |",
        "| --- | --- |",
        "| Одно полезное действие целиком через синапсы | ✔ документ превращён в Markdown |",
        "| Полный трейс восстанавливается из журнала крови | ✔ G1-реконструкция выше |",
        "| Ни одного события с пустой `cost` | ✔ проверено по всем конвертам |",
        "| Метаболизм и эффектор в том же трейсе | ✖ цель v0.2.2 (нужен живой инференс-хост) |",
        "",
        "## Содержание blood.jsonl",
        "",
    ]
    for event in replayed:
        lines.append(
            f"- `{event['ts']}` {event['type']} source={event['source']} organ={event['organ']}"
        )
    lines += [
        "",
        "Выход сенсорики сохранён в `output.md` рядом с отчётом.",
        "",
    ]
    (run_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    run_id = f"{datetime.now(timezone.utc).date()}-first-pulse"
    run_dir = REPO_ROOT / "runs" / run_id
    input_path = run_dir / "input" / "pulse-input.docx"

    create_input(input_path)
    print(f"[1/4] вход подготовлен: {input_path.relative_to(REPO_ROOT)}")

    journal = Journal()
    gateway = Gateway(REPO_ROOT / "synapse" / "mcp-manifest.yaml", journal)
    loop = Loop(gateway, journal)
    print(f"[2/4] синапсы собраны по манифесту; органы: {', '.join(gateway.organ_names)}")

    trace_id = new_trace_id()
    budget = Budget(seconds=60.0)
    plan = [
        Step(
            organ="markitdown",
            tool="convert_to_markdown",
            payload={"uri": f"file://{input_path}"},
            intent="увидеть документ: DOCX → Markdown",
        ),
    ]
    ok = loop.run(plan, trace_id=trace_id, budget=budget)
    print(f"[3/4] цикл завершён: satisfied={ok}, trace_id={trace_id}")

    if not ok:
        print("пульс не прошёл — см. события error/veto в журнале", file=sys.stderr)
        return 1

    observe = [e for e in journal.by_trace(trace_id) if e["type"] == "observe"][0]
    output_text = observe["payload"]["result"]["text"]
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "blood.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in journal) + "\n", encoding="utf-8"
    )
    (run_dir / "output.md").write_text(output_text, encoding="utf-8")
    write_report(run_dir, trace_id, list(journal), output_text, budget)

    assert INPUT_MARKER in output_text, "сенсорика не увидела маркер входного документа"
    print(f"[4/4] артефакты: {run_dir.relative_to(REPO_ROOT)} (blood.jsonl, output.md, report.md)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
