# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Живые органы арены А/Б (волна №10, W-0011): настоящий LLM и настоящий fetch.

- ZaiAnswer — орган познания: читает файлы сам (fs: read-write), решает задачу
  живым GLM через `z-ai` CLI (process: spawn, сеть — у детёныша), записывает
  отчёт на диск. Поле `broken_sector` манифеста — живой отказ органа:
  «повреждённое чтение» помеченного файла роняет invoke (резерв цел).
- Scraper — орган сверки: настоящий urllib-запрос (в манифесте network: none —
  страж обязан прервать ДО соединения; голый диспетчер соединится по-настоящему).

Цена — настоящая: usage от GLM (prompt/completion tokens), у инструментов —
длина payload; секунды мерит шлюз (wall-clock), адаптер отдаёт свою оценку.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

from blood.envelope import Cost

ZAI = "z-ai"
CURSED_MARK = "cursed"  # метка «битого сектора»: орган с broken_sector падает на таком файле

ANSWER_SYSTEM = (
    "Ты — орган познания организма COMMONS. Тебе дали вопрос и содержимое файлов. "
    "Реши задачу по этим данным, ничего не выдумывай. Верни ТОЛЬКО текст отчёта: "
    "строка «Итоговая сумма: <N> руб.» и строка «Самая дорогая покупка: <название> (<N> руб.)»."
)


def zai_chat(prompt: str, system: str, *, timeout: float = 240.0, workdir: Path | None = None) -> tuple[str, Cost]:
    """Живой вызов GLM через z-ai CLI. Возвращает (текст, настоящая цена)."""
    started = time.monotonic()
    out_path = Path(tempfile.mkstemp(prefix="w10-ab-zai-", suffix=".json", dir=workdir)[1]) if workdir else None
    argv = [ZAI, "chat", "-p", prompt, "-s", system]
    if out_path is not None:
        argv += ["-o", str(out_path)]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)  # process: spawn — заявлено в манифесте
    try:
        if proc.returncode != 0:
            raise RuntimeError(f"z-ai упал (код {proc.returncode}): {(proc.stderr or proc.stdout).strip()[:200]}")
        if out_path is not None:
            raw = out_path.read_text(encoding="utf-8")
        else:
            raw = proc.stdout  # без -o CLI печатает прогресс до JSON — честно отрезаем всё до первой скобки
            raw = raw[raw.find("{"):] if "{" in raw else ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"z-ai ответил не-JSON ({exc}): хвост {(proc.stdout + proc.stderr).strip()[-200:]!r}") from None
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        cost = Cost(
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
            seconds=round(time.monotonic() - started, 6),
        )
        return text, cost
    finally:
        if out_path is not None:
            out_path.unlink(missing_ok=True)


class ZaiAnswer:
    """Орган познания: ответ живым GLM + запись отчёта на диск (fs: read-write)."""

    def __init__(self, entry: dict[str, Any]) -> None:
        self.entry = entry
        self.broken = bool(entry.get("broken_sector"))
        self.usage_log: list[Cost] = []

    def health(self) -> bool:
        return shutil.which(ZAI) is not None

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Cost]:
        if tool != "answer":
            raise AssertionError(f"ZaiAnswer не умеет {tool!r}")
        files = [Path(p) for p in (payload.get("files") or [])]
        if not files or "question" not in payload or "out" not in payload:
            raise RuntimeError("payload обязан быть question, files, out")
        pieces: list[str] = []
        for path in files:
            if self.broken and CURSED_MARK in path.name:
                raise RuntimeError(f"орган llm: повреждённое чтение {path.name} (живой отказ органа)")
            pieces.append(f"--- {path.name} ---\n" + path.read_text(encoding="utf-8").strip())
        prompt = (
            str(payload["question"]).strip()
            + "\n\nСодержимое файлов:\n\n"
            + "\n\n".join(pieces)
            + f"\n\nЗапиши отчёт ровно в файл {payload['out']} — но сначала верни его текст мне."
        )
        out = Path(payload["out"])
        out.parent.mkdir(parents=True, exist_ok=True)  # до вызова: он же workdir файла ответа CLI
        answer, cost = zai_chat(prompt, ANSWER_SYSTEM, workdir=out.parent)
        self.usage_log.append(cost)
        out.write_text(answer, encoding="utf-8")
        return {"answer": answer, "written": str(out), "files_read": [p.name for p in files]}, cost


class Scraper:
    """Орган сверки: настоящий сетевой запрос. В манифесте network: none."""

    def __init__(self, entry: dict[str, Any]) -> None:
        self.entry = entry
        self.usage_log: list[Cost] = []

    def health(self) -> bool:
        return True

    def invoke(self, tool: str, payload: dict[str, Any]) -> tuple[Any, Cost]:
        if tool != "fetch":
            raise AssertionError(f"Scraper не умеет {tool!r}")
        url = payload.get("url")
        if not url:
            raise RuntimeError("payload обязан быть url")
        started = time.monotonic()
        with urllib.request.urlopen(url, timeout=5) as resp:  # socket.connect — при network: none страж прервёт ДО
            body = resp.read().decode("utf-8")
        cost = Cost(tokens_in=len(str(payload)), tokens_out=len(body), seconds=round(time.monotonic() - started, 6))
        self.usage_log.append(cost)
        return {"control": body.strip()}, cost
