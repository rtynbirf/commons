"""Пульс организма: сенсорика + метаболизм в одном трейсе — полный DoD M1.

Два органа в одном trace_id, всё через синапсы:
  1. markitdown (сенсорика): документ → Markdown;
  2. llama.cpp (метаболизм): Markdown → сжатие смысла; токены попадают в кровь
     (tokens_in ← tokens_evaluated, tokens_out ← tokens_predicted сервера).

Предусловия на машине организма:
  pip install markitdown-mcp python-docx;  llama-server на ${LLAMA_SERVER_URL:-http://127.0.0.1:8080}
Пример поднятия метаболизма:
  llama-server -m qwen2.5-0.5b-instruct-q4_k_m.gguf --host 127.0.0.1 --port 8080 -t 4

Артефакты: runs/<дата>-organism-pulse/ (blood.jsonl, output.md, report.md).
Запуск из корня репо: python3 scripts/organism_pulse.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import new_trace_id  # noqa: E402
from blood.journal import Journal  # noqa: E402
from brainstem.loop import Budget, Loop, Step  # noqa: E402
from synapse.gateway import Gateway  # noqa: E402

DOC_HEADING = "Задание organism-pulse: смысл в обмене"
DOC_PARAGRAPHS = [
    "COMMONS — организм из открытых органов человечества: органы живут на upstream, единым остаётся обмен.",
    "Ствол мозга ведёт цикл PLAN-ACT-OBSERVE-REFLECT, синапсы пропускают только вызовы из манифеста, кровь считает цену каждого события.",
    "Сенсорика превращает документы в Markdown, метаболизм думает локально, эффекторы действуют, иммунитет не пускает чужую лицензию внутрь тела.",
]
SUMMARY_PROMPT = (
    "Ниже документ. Ответь одной короткой фразой, о чём он, без вступлений.\n\n"
    "=== ДОКУМЕНТ ===\n{doc}\n=== КОНЕЦ ===\n\nОдна фраза о содержании:"
)


def create_input(path: Path) -> None:
    from docx import Document

    doc = Document()
    doc.add_heading(DOC_HEADING, 0)
    for paragraph in DOC_PARAGRAPHS:
        doc.add_paragraph(paragraph)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)


def write_report(run_dir: Path, trace_id: str, events: list[dict], summary: str, budget: Budget) -> None:
    from blood.envelope import validate

    replayed = [json.loads(line) for line in (run_dir / "blood.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    for envelope in replayed:
        validate(envelope)

    organs = {event["organ"] for event in replayed if event["type"] == "act"}
    acts = [event for event in replayed if event["type"] == "act"]
    totals = {
        "tokens_in": sum(e["cost"]["tokens_in"] for e in replayed),
        "tokens_out": sum(e["cost"]["tokens_out"] for e in replayed),
        "seconds": round(sum(e["cost"]["seconds"] for e in replayed), 6),
    }

    lines = [
        "# Пульс организма: сенсорика + метаболизм (отчёт)",
        "",
        f"- trace_id: `{trace_id}`",
        f"- дата: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- органы в трейсе: {', '.join(sorted(organs))}",
        "",
        "## Что произошло",
        "",
        "Один трейс, два органа, ноль вызовов мимо синапсов:",
        "1. markitdown (MCP stdio) — DOCX → Markdown;",
        "2. llama.cpp (HTTP /completion) — Markdown → сжатие смысла; токены посчитаны сервером и легли в кровь.",
        "Цикл не знает органов; замену llama.cpp ↔ ollama можно сделать правкой манифеста (G2).",
        "",
        "## Реконструкция из крови (G1)",
        "",
        f"- конвертов: {len(replayed)}, все валидны по схеме; trace_id один: `{len({e['trace_id'] for e in replayed}) == 1}`",
        f"- последовательность: `{' → '.join(e['type'] for e in replayed)}`",
        f"- `cost` заполнен во всех конвертах: `{all(set(e['cost']) == {'tokens_in', 'tokens_out', 'seconds'} for e in replayed)}`",
        "",
        "## Цена (G3)",
        "",
        f"- бюджет: seconds ≤ {budget.seconds}",
        f"- израсходовано: tokens_in={totals['tokens_in']}, tokens_out={totals['tokens_out']}, seconds={totals['seconds']}",
        "",
    ]
    for act in acts:
        lines.append(f"- `{act['organ']}`: {act['cost']['tokens_in']} ток. внутрь, {act['cost']['tokens_out']} ток. наружу, {act['cost']['seconds']} c")
    lines += [
        "",
        "## Ответ метаболизма",
        "",
        "```text",
        summary.strip(),
        "```",
        "",
        "## Чек-лист DoD M1",
        "",
        "| Требование DoD | Статус |",
        "| --- | --- |",
        "| Одно полезное действие целиком через синапсы | ✔ сенсорика + метаболизм, один трейс |",
        "| Полный трейс восстанавливается из журнала крови | ✔ G1-реконструкция выше |",
        "| Ни одного события с пустой `cost` | ✔ токены и секунды по всем конвертам |",
        "| Метаболизм и эффектор в том же трейсе | ✖ эффектор browser-use — приёмка S4 (спайк на хосте с браузером) |",
        "",
        "## Содержание blood.jsonl",
        "",
    ]
    for event in replayed:
        lines.append(f"- `{event['ts']}` {event['type']} source={event['source']} organ={event['organ']}")
    lines.append("")
    (run_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    run_id = f"{datetime.now(timezone.utc).date()}-organism-pulse"
    run_dir = REPO_ROOT / "runs" / run_id
    input_path = run_dir / "input" / "organism-pulse.docx"

    create_input(input_path)
    print(f"[1/4] вход: {input_path.relative_to(REPO_ROOT)}")

    journal = Journal()
    gateway = Gateway(REPO_ROOT / "synapse" / "mcp-manifest.yaml", journal)
    loop = Loop(gateway, journal)
    print(f"[2/4] синапсы: {', '.join(gateway.organ_names)}")

    trace_id = new_trace_id()
    budget = Budget(seconds=120.0)
    # Первый шаг выполняется раньше второго, чтобы метаболизм увидел выход сенсорики:
    # PLAN-ACT-OBSERVE даёт результат шага 1, из него собирается промпт шага 2.
    doc_step = Step(
        organ="markitdown",
        tool="convert_to_markdown",
        payload={"uri": f"file://{input_path}"},
        intent="увидеть документ: DOCX → Markdown",
    )
    ok = loop.run([doc_step], trace_id=trace_id, budget=budget)
    if not ok:
        print("сенсорика не прошла", file=sys.stderr)
        return 1

    markdown = [e for e in journal.by_trace(trace_id) if e["type"] == "observe"][0]["payload"]["result"]["text"]
    think_step = Step(
        organ="llama.cpp",
        tool="completion",
        payload={"prompt": SUMMARY_PROMPT.format(doc=markdown), "n_predict": 64},
        intent="сжать смысл документа одной фразой",
    )
    ok = loop.run([think_step], trace_id=trace_id, budget=budget)
    if not ok:
        print("метаболизм не прошёл", file=sys.stderr)
        return 1

    events = list(journal.by_trace(trace_id))
    summary = [e for e in events if e["type"] == "observe" and e["organ"] == "llama.cpp"][0]["payload"]["result"]["response"]
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "blood.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n", encoding="utf-8"
    )
    (run_dir / "output.md").write_text(markdown + "\n\n---\n\n## Ответ метаболизма\n\n" + summary + "\n", encoding="utf-8")
    write_report(run_dir, trace_id, events, summary, budget)
    print(f"[3/4] метаболизм: {summary.strip()[:80]}…")
    print(f"[4/4] артефакты: {run_dir.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
