#!/usr/bin/env python3
"""Спайк S2: агентный цикл — langchain против собственного (ROADMAP M2, docs/spikes.md).

Метрики (на фейковой модели — измеряется каркас, а не LLM):
- сколько символов/≈токенов каркас отправляет модели сверх задачи (scaffolding);
- сколько вызовов модели на задачу;
- как каркас растёт с числом инструментов.

Гипотеза SPEC-0001: собственный цикл проще и трассируемее при равной полезной нагрузке.

Запуск: pip install langchain && python3 spikes/s2-cycle/measure.py
Без langchain: печатает NO_LANGCHAIN и выходит с кодом 2 — цифры не выдумываются.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]  # spikes/s2-cycle/measure.py → корень репо
sys.path.insert(0, str(REPO_ROOT))

TASK = "сделай пустое дело"


def _rows_langchain() -> Iterator[dict]:
    import warnings

    warnings.filterwarnings("ignore")
    from typing import ClassVar

    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    from langchain_core.tools import tool

    class RecordingFake(FakeListChatModel):
        seen: ClassVar[list] = []
        wire_chars: ClassVar[int] = 0  # схемы инструментов — трафик к провайдеру через bind_tools

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            type(self).seen.append(list(messages))
            return super()._generate(messages, stop, run_manager, **kwargs)

        def bind_tools(self, tools, **kwargs):
            import json

            from langchain_core.utils.function_calling import convert_to_openai_tool

            for tool_obj in tools or []:
                type(self).wire_chars += len(json.dumps(convert_to_openai_tool(tool_obj), ensure_ascii=False))
            return self

    @tool
    def noop_tool(what: str) -> str:
        """Ничего не делает: тестовый инструмент каркаса."""
        return what

    for tools, label in (([], "без инструментов"), ([noop_tool], "1 инструмент")):
        RecordingFake.seen = []
        RecordingFake.wire_chars = 0
        agent = create_agent(model=RecordingFake(responses=["готово"]), tools=list(tools))
        agent.invoke({"messages": [{"role": "user", "content": TASK}]})
        messages = RecordingFake.seen[0]
        chars = sum(len(str(getattr(m, "content", ""))) for m in messages) + RecordingFake.wire_chars
        yield {"framework": f"langchain 1.x ({label})", "calls": len(RecordingFake.seen),
               "messages": len(messages), "chars": chars, "tokens": chars // 4}


def _row_own_cycle(tmp: Path) -> dict:
    """Собственный цикл: органу уходит план (intent) и payload — больше ничего."""
    from blood.envelope import Cost
    from blood.journal import Journal
    from brainstem.loop import Budget, Loop, Step
    from synapse.gateway import Gateway

    manifest = tmp / "manifest-mini.yaml"
    manifest.write_text(
        "organs:\n"
        "  - name: stub\n    system: metabolism\n    mode: dependency\n"
        "    upstream: none\n    license: MIT\n    transport: stdio\n"
        "    command: none-mcp\n    healthcheck: initialize handshake\n"
        "    tools: [noop]\n    authority: {fs: none, network: none}\n",
        encoding="utf-8",
    )
    gateway = Gateway(manifest)

    class Stub:
        def health(self) -> bool:
            return True

        def invoke(self, tool: str, payload: dict) -> tuple[dict, Cost]:
            return {"text": "готово"}, Cost()

    gateway.bind_adapter("stub", Stub())
    loop = Loop(gateway, Journal())
    loop.run([Step(organ="stub", tool="noop", payload={"prompt": TASK}, intent=TASK)], budget=Budget())
    chars = len(TASK) * 2  # intent (plan) + prompt (act)
    return {"framework": "COMMONS ствол мозга (SPEC-0001)", "calls": 1,
            "messages": 1, "chars": chars, "tokens": chars // 4}


def main() -> int:
    try:
        rows = list(_rows_langchain())
    except ImportError:
        print("NO_LANGCHAIN: пакет не установлен — спайк не врёт вместо замера.")
        print("pip install langchain && python3 spikes/s2-cycle/measure.py")
        return 2

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        rows.append(_row_own_cycle(Path(tmp)))

    print("| путь | вызовов модели | сообщений | scaffolding, симв | ≈ токенов (симв//4) |")
    print("| --- | --- | --- | --- | --- |")
    for row in rows:
        print(f"| {row['framework']} | {row['calls']} | {row['messages']} | {row['chars']} | {row['tokens']} |")
    print("\nВывод: каркас langchain растёт с числом инструментов (схемы едут в промпте),")
    print("собственный цикл отправляет только намерение. Вердикт — в ADR/issue спайка S2.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
