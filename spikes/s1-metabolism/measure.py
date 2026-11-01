#!/usr/bin/env python3
"""Спайк S1: метаболизм — ollama vs llama.cpp на одной модели (ROADMAP M2, ADR-0004).

Замеряет на живом хосте: cold start, TTFT (time to first token), throughput (tok/s),
полное время генерации. Результат — markdown-таблица для ADR/issue.

Запуск (серверы должны быть подняты заранее):
  ollama serve &                                 # или OLLAMA_HOST удалённый
  llama-server -m модель.gguf --port 8080 &
  OLLAMA_HOST=http://127.0.0.1:11434 \
  LLAMA_SERVER_URL=http://127.0.0.1:8080 \
  python3 spikes/s1-metabolism/measure.py --model qwen2.5:0.5b --runs 3

Правила спайка (docs/spikes.md):
- одна и та же модель (одинаковые веса, q4), температура 0, фиксированный промпт;
- каждый сервер: 1 cold start прогон + N тёплых; в таблицу — медиана тёплых;
- харнесс не выдумывает цифры: без серверов печатает NO_SERVER и выходит с кодом 2.

Зависимости: только стандартная библиотека Python 3.10+.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request

PROMPT = "Ответь одним абзацем: что такое commons? Определение плюс пример."
N_PREDICT = 120


def _post(url: str, body: dict, timeout: float = 600.0) -> tuple[list[bytes], float, float]:
    """POST со стримом: возвращает (строки ответа, ttft, полное время). Секунды."""
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    started = time.monotonic()
    lines: list[bytes] = []
    ttft = -1.0
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for raw in response:
            if not raw.strip():
                continue
            if ttft < 0:
                ttft = time.monotonic() - started
            lines.append(raw.strip())
    return lines, ttft, time.monotonic() - started


def measure_ollama(host: str, model: str, runs: int) -> dict:
    """POST {host}/api/generate со стримом; финальный объект несёт eval_count/eval_duration."""
    host = host.rstrip("/")
    rows = []
    for index in range(runs + 1):
        lines, ttft, wall = _post(f"{host}/api/generate", {"model": model, "prompt": PROMPT, "stream": True})
        final = json.loads(lines[-1]) if lines else {}
        eval_count = final.get("eval_count") or 0
        eval_duration = final.get("eval_duration") or 0  # наносекунды
        throughput = eval_count / (eval_duration / 1e9) if eval_count and eval_duration else 0.0
        rows.append({
            "cold": index == 0,
            "ttft": ttft,
            "wall": wall,
            "tokens": eval_count,
            "tok_s": round(throughput, 1),
        })
    return _summary("ollama", host, model, rows)


def measure_llama(url: str, runs: int) -> dict:
    """POST {url}/completion со стримом; финальный объект несёт timings."""
    url = url.rstrip("/")
    rows = []
    for index in range(runs + 1):
        lines, ttft, wall = _post(f"{url}/completion", {"prompt": PROMPT, "n_predict": N_PREDICT, "stream": True})
        final = json.loads(lines[-1].decode()) if lines else {}
        timings = final.get("timings") or {}
        rows.append({
            "cold": index == 0,
            "ttft": ttft,
            "wall": wall,
            "tokens": timings.get("predicted_n", 0),
            "tok_s": round(timings.get("predicted_per_second", 0.0), 1),
        })
    return _summary("llama.cpp", url, "веса, загруженные в llama-server", rows)


def _summary(organ: str, endpoint: str, model: str, rows: list[dict]) -> dict:
    warm = rows[1:] if len(rows) > 1 else rows
    return {
        "organ": organ,
        "endpoint": endpoint,
        "model": model,
        "cold_start": round(rows[0]["wall"], 3),
        "cold_ttft": round(rows[0]["ttft"], 3),
        "ttft_median": round(statistics.median(r["ttft"] for r in warm), 3),
        "wall_median": round(statistics.median(r["wall"] for r in warm), 3),
        "tokens_median": int(statistics.median(r["tokens"] for r in warm)),
        "tok_s_median": round(statistics.median(r["tok_s"] for r in warm), 1),
    }


def table(results: list[dict]) -> str:
    head = (
        "| орган | endpoint | модель | cold start, с | TTFT (медиана), с |"
        " генерация (медиана), с | токенов | tok/s |"
    )
    sep = "| --- | --- | --- | --- | --- | --- | --- | --- |"
    body = [
        f"| {r['organ']} | {r['endpoint']} | {r['model']} | {r['cold_start']} | {r['ttft_median']}"
        f" | {r['wall_median']} | {r['tokens_median']} | {r['tok_s_median']} |"
        for r in results
    ]
    return "\n".join([head, sep, *body])


def main() -> int:
    parser = argparse.ArgumentParser(description="Спайк S1: ollama vs llama.cpp")
    parser.add_argument("--model", default="qwen2.5:0.5b", help="модель ollama (одинаковые веса для обоих)")
    parser.add_argument("--runs", type=int, default=3, help="тёплых прогонов на орган")
    args = parser.parse_args()

    ollama_host = os.environ.get("OLLAMA_HOST")
    llama_url = os.environ.get("LLAMA_SERVER_URL")
    results: list[dict] = []

    if ollama_host:
        results.append(measure_ollama(ollama_host, args.model, args.runs))
    if llama_url:
        results.append(measure_llama(llama_url, args.runs))

    if not results:
        print("NO_SERVER: ни одного живого сервера метаболизма — спайк не врёт вместо замера.")
        print("Подними ollama serve и/или llama-server и задай OLLAMA_HOST / LLAMA_SERVER_URL.")
        return 2

    print(table(results))
    print("\nВердикт заносится в ADR/issue: критерии замены — SPEC-0001 G2, спайк docs/spikes.md S1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
