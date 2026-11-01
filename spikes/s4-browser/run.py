#!/usr/bin/env python3
"""Спайк S4: прогон сценариев browser-use через контракт MCP-stdio (ROADMAP M2).

Скелет приёмки: исполняет декларативные шаги scenarios.yaml через тот же адаптер,
что стоит за markitdown (MCPStdioAdapter) — орган подключается правкой манифеста.
На хосте без браузера печатает NO_BROWSER (код 2) — цифры не выдумываются.

Запуск: python3 spikes/s4-browser/run.py --command browser-use-mcp --runs 5
"""

from __future__ import annotations

import argparse
import shutil
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from blood.envelope import Cost  # noqa: E402
from synapse.adapters.mcp_stdio import MCPStdioAdapter  # noqa: E402

SCENARIOS = Path(__file__).resolve().parent / "scenarios.yaml"


def run_scenario(adapter: MCPStdioAdapter, scenario: dict[str, Any], runs: int) -> dict:
    """Пытается исполнить шаги сценария; считает долю успешных прогонов и время."""
    durations: list[float] = []
    successes = 0
    for _ in range(runs):
        started = time.monotonic()
        ok = True
        for step in scenario["steps"]:
            try:
                result, _cost = adapter.invoke(step, {})  # аргументы шага — задача S5/v0.3
                if isinstance(result, dict) and result.get("is_error"):
                    ok = False
                    break
            except Exception:  # noqa: BLE001 — отказ шага = неуспех прогона
                ok = False
                break
        durations.append(time.monotonic() - started)
        successes += int(ok)
    return {
        "id": scenario["id"],
        "success_rate": successes / runs,
        "p50": round(statistics.median(durations), 1),
        "p95": round(sorted(durations)[int(0.95 * (len(durations) - 1))], 1),
        "limit": scenario["limit"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Спайк S4: browser-use end-to-end")
    parser.add_argument("--command", default="browser-use-mcp", help="команда MCP-сервера браузера")
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()

    if shutil.which(args.command.split()[0]) is None:
        print(f"NO_BROWSER: {args.command!r} не на PATH — спайк не врёт вместо замера.")
        print("Подними браузерный MCP-сервер (pip install browser-use) и повтори.")
        return 2

    scenarios = yaml.safe_load(SCENARIOS.read_text(encoding="utf-8"))["scenarios"]
    adapter = MCPStdioAdapter({"command": args.command, "authority": {"network": "allowlist", "fs": "downloads-dir"}})
    if not adapter.health():
        print("NO_BROWSER: сервер не прошёл initialize handshake.")
        return 2

    print("| сценарий | успех | p50, с | p95, с | лимит, с |")
    print("| --- | --- | --- | --- | --- |")
    passed = 0
    for scenario in scenarios:
        row = run_scenario(adapter, scenario, args.runs)
        passed += int(row["success_rate"] >= 0.8 and row["p95"] <= row["limit"])
        print(f"| {row['id']} | {row['success_rate']:.0%} | {row['p50']} | {row['p95']} | {row['limit']} |")
    print(f"\nПройдено {passed}/{len(scenarios)}; вердикт — в spikes/s4-browser/README.md")
    adapter._ensure_process().terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
