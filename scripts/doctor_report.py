#!/usr/bin/env python3
"""Память воротов (волна-9, 0.23.0): таблица из машиночитаемого отчёта.

Читает JSON-отчёт доктора (`scripts/doctor.py --json > doctor-report.json`)
и печатает человекочитаемую markdown-таблицу — оба воркфлоу (ci.yml,
fleas.yml) направляют её в $GITHUB_STEP_SUMMARY. Каждый прогон ворот
оставляет след, который перечитывают и человек (W-0002: видеть по крови,
а не по обещаниям), и коллега-агент (W-0017: читать ворота без человека).

Синтез мировой практики (свип 2026-11-02): lychee-action — json-отчёт +
артефакт + GitHub job summary на каждый прогон; след не живёт только в
логах, по нему видна динамика.

Запуск: python3 scripts/doctor_report.py doctor-report.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def render(report: dict) -> str:
    """Отчёт → markdown-таблица: гейт | ok | блохи, и честный итог."""
    lines = ["## Доктор дома", "", "| гейт | ok | блохи |", "|---|---|---|"]
    for gate in report.get("gates", []):
        lines.append(f"| {gate['gate']} | {gate['ok']} | {len(gate['fleas'])} |")
    lines.append("")
    lines.append(
        f"**Итог: {report.get('total_ok', 0)} ok, {report.get('total_fleas', 0)} failed**"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = list(argv) if argv else []
    if not args:
        print("использование: doctor_report.py <doctor-report.json>", file=sys.stderr)
        return 2
    report = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    print(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
