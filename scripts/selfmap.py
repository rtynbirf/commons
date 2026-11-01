#!/usr/bin/env python3
"""Selfmap: организм рисует себя сам (Definition of One, п.4).

Читает живые реестры (organs/registry.yaml + synapse/mcp-manifest.yaml)
и генерирует docs/selfmap.md — карту органов в mermaid.

Запуск: python3 scripts/selfmap.py
Результат коммитится; ручные правки selfmap.md запрещены — правь реестры.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "organs" / "registry.yaml"
MANIFEST = ROOT / "synapse" / "mcp-manifest.yaml"
TARGET = ROOT / "docs" / "selfmap.md"

SYSTEM_TITLES = {
    "genome": "Геном",
    "brainstem": "Ствол мозга",
    "synapse": "Синапсы",
    "blood": "Кровь",
    "metabolism": "Метаболизм",
    "memory": "Память",
    "senses": "Сенсорика",
    "effectors": "Эффекторы",
    "nerves_alt": "Нервные альтернативы",
    "glands": "Железы",
    "skin": "Кожа",
    "selfmap": "Самоописание",
    "remote": "Удалённость",
    "immune_knowledge": "Иммунитет (знания)",
    "substrate": "Субстрат",
    "reproduction": "Репродукция",
}

SYSTEM_ORDER = list(SYSTEM_TITLES)

EXTERNAL_MODES = {"external", "substrate", "education"}

LICENSE_OK = {"MIT", "Apache-2.0", "BSD-3-Clause", "MIT OR Apache-2.0", "CC0-1.0"}


def slug(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name).strip("_")


def main() -> int:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    manifest_tools = {o["name"]: set(o["tools"]) for o in manifest.get("organs", [])}

    lines: list[str] = [
        "# Самоописание организма",
        "",
        "<!-- AUTO-GENERATED: python3 scripts/selfmap.py — ручные правки запрещены, правь реестры -->",
        "",
        "Сгенерировано из живых реестров: `organs/registry.yaml` + `synapse/mcp-manifest.yaml`.",
        "",
        "```mermaid",
        "flowchart LR",
    ]

    organs = registry.get("organs", [])
    wired = {o["repo"].rsplit("/", 1)[-1] for o in organs if o["repo"].rsplit("/", 1)[-1] in manifest_tools}

    for system in SYSTEM_ORDER:
        group = [o for o in organs if o.get("system") == system]
        if not group:
            continue
        title = SYSTEM_TITLES[system]
        lines.append(f"  subgraph {system}[\"{title}\"]")
        for organ in group:
            name = organ["repo"].rsplit("/", 1)[-1]
            node = slug(name)
            license_ = str(organ.get("license_pre", "?"))
            mode = organ.get("mode", "?")
            tools = manifest_tools.get(name)
            label = f"{name}<br/>{license_} · {mode}"
            if tools:
                label += f"<br/>MCP: {', '.join(sorted(tools))}"
            lines.append(f'    {node}["{label}"]')
            if name in wired:
                lines.append(f'    {node}:::wired')
            elif organ.get("mode") in EXTERNAL_MODES or license_ not in LICENSE_OK:
                lines.append(f'    {node}:::outside')
        lines.append("  end")

    lines += [
        '  brainstem_core["Ствол мозга<br/>SPEC-0001"]:::own',
        '  synapse_gw["Синапсы: MCP-шлюз<br/>SPEC-0002"]:::own',
        '  blood_jr["Кровь: конверт+журнал<br/>SPEC-0003"]:::own',
        "  synapse_gw --> brainstem_core",
        "  brainstem_core --> blood_jr",
        "  synapse_gw --> blood_jr",
        "]();",
        "",
        "  classDef own fill:#1b6e5a,color:#fff,stroke:#0d3f34;",
        "  classDef wired fill:#2f7bd6,color:#fff,stroke:#1a4a8a;",
        "  classDef outside fill:#9aa4ad,color:#222,stroke:#6b757e,stroke-dasharray:4 2;",
        "```",
        "",
        "## Легенда",
        "",
        "- **Зелёный** — собственный код ядра (спеки SPEC-0001..0003).",
        "- **Синий** — органы, объявленные в манифесте синапсов (доступны телу).",
        "- **Серый пунктир** — внешний узел, субстрат или обучение: в тело не входит.",
        "",
        "Регенерация: `python3 scripts/selfmap.py`.",
    ]

    TARGET.write_text("\n".join(lines).replace("]();", "") + "\n", encoding="utf-8")
    print(f"selfmap: {TARGET} ({len(organs)} органов, {len(wired)} в манифесте)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
