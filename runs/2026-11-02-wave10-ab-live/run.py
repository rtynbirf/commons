# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Живой А/Б «с организмом / без» (волна №10, W-0011) — дирижёр арены.

Одна задача, равные условия, равные критерии провала (зафиксированы заранее):
  К1 задача решена — out/answer.md содержит верную сумму и самую дорогую покупку;
  К2 отказной шаг восстановлен — «битое чтение» у llm обслужено резервом (А) /
     потеряно молча (Б: резерв есть, но голому диспетчеру неоткуда знать про замены);
  К3 нарушение полномочий видно ДО факта — fetch при network: none прерван стражем,
     локальный сервис-свидетель не видел ни одного соединения (А) / fetch исполнен
     по-настоящему, соединение состоялось, содержимое попало в результат (Б);
  К4 цена — настоящие токены GLM и секунды (А: по крови; Б: по логам адаптеров);
  К5 артефакты — полная кровь трейса (А) / ноль записей (Б).

Группы: А — ствол+синапсы+кровь+страж; Б — голый диспетчер из тех же классов органов.
По 3 живых семени на группу: живая модель не детерминирована — равенство условий,
не равенство байтов (байт-в-байт остался на фейках, wave5).

Запуск из корня репо: python runs/2026-11-02-wave10-ab-live/run.py
Артефакты: blood.jsonl (только группа А — у Б крови нет), stats.json, plans.json, report.md.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
RUN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(RUN_DIR))  # аб_органы арены — уникальное имя модуля (в корне есть пакет organs/)

import yaml  # noqa: E402

BLOOD_PATH = RUN_DIR / "blood.jsonl"
STATS_PATH = RUN_DIR / "stats.json"
PLANS_PATH = RUN_DIR / "plans.json"

NOTES: dict[str, str] = {
    "notes/a.txt": "Молоток — 850 руб.\nГвозди — 120 руб.\n",
    "notes/b.txt": "Пила — 1450 руб.\n",
    "notes/cursed.txt": "Дрель — 3200 руб.\nСвёрла — 460 руб.\n",
    "notes/d.txt": "Отвёртка — 210 руб.\n",
}

VERDICTS: list[str] = []


def verdict(kind: str, text: str) -> None:
    marker = {"g": "[ЗЕЛЁНО]", "r": "[КРАСНО]", "f": "[ФАКТ]"}[kind]
    line = f"{marker} {text}"
    print(line)
    VERDICTS.append(line)


# --- локальный сервис-свидетель: считает каждое настоящее соединение ---

class ControlServer:
    def __init__(self) -> None:
        hits: list[str] = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 — API http.server
                hits.append(self.path)
                body = "контрольное число: 4242".encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: Any) -> None:  # тишина: свидетель молчит, счёт ведёт список
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.hits = hits
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_port}/control"


# --- рабочее место и манифест арены (одинаковы для обеих групп) ---

def build_workspace(tmp: Path) -> Path:
    workspace = tmp / "workspace"
    for rel, text in NOTES.items():
        path = workspace / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    (workspace / "out").mkdir(parents=True, exist_ok=True)
    return workspace


def build_manifest(tmp: Path) -> Path:
    doc = {
        "version": "w10-ab",
        "updated": "2026-11-02",
        "transport_default": "stdio",
        "organs": [
            {
                "name": "llm", "system": "cognition", "mode": "dependency",
                "upstream": "zai://glm-4-plus", "license": "Apache-2.0",
                "transport": "stdio", "command": "z-ai", "healthcheck": "z-ai в PATH",
                "tools": ["answer"],
                "authority": {"fs": "read-write", "network": "any", "process": "spawn"},
                "adapter": "ab_organs:ZaiAnswer", "broken_sector": True,
            },
            {
                "name": "llm-b", "system": "cognition", "mode": "dependency",
                "upstream": "zai://glm-4-plus", "license": "Apache-2.0",
                "transport": "stdio", "command": "z-ai", "healthcheck": "z-ai в PATH",
                "tools": ["answer"],
                "authority": {"fs": "read-write", "network": "any", "process": "spawn"},
                "adapter": "ab_organs:ZaiAnswer", "broken_sector": False,
            },
            {
                "name": "scraper", "system": "senses", "mode": "dependency",
                "upstream": "local://control", "license": "Apache-2.0",
                "transport": "stdio", "command": "curl", "healthcheck": "локальный сервис",
                "tools": ["fetch"],
                "authority": {"fs": "read-only", "network": "none", "process": "none"},
                "adapter": "ab_organs:Scraper",
            },
        ],
        "substitutions": {"llm": ["llm-b"]},
    }
    path = tmp / "mcp-manifest.yaml"
    path.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return path


# --- живые прогоны ---

def run_one(group: str, seed: int, workspace: Path, manifest: Path, url: str, tmp: Path) -> dict[str, Any]:
    stats_path = tmp / f"stats-{group}-{seed}.json"
    plans_path = tmp / f"plans-{group}-{seed}.json"
    argv = [
        sys.executable, str(RUN_DIR / "group.py"),
        "--group", group, "--seed", str(seed),
        "--workspace", str(workspace), "--url", url,
        "--manifest", str(manifest), "--blood", str(BLOOD_PATH),
        "--stats", str(stats_path), "--plans", str(plans_path),
    ]
    proc = subprocess.run(argv, capture_output=True, text=True, cwd=str(workspace),
                          timeout=900)  # cwd = живая территория: относительные пути плана resolve'ятся на месте
    if proc.returncode != 0:
        return {"group": group, "seed": seed, "subprocess_error": (proc.stderr or proc.stdout).strip()[-500:]}
    stats: dict[str, Any] = json.loads(stats_path.read_text(encoding="utf-8"))
    stats["model_raw"] = json.loads(plans_path.read_text(encoding="utf-8"))
    return stats


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="w10-ab-"))
    BLOOD_PATH.unlink(missing_ok=True)  # свежая кровь прогонов этого запуска
    server = ControlServer()
    server.start()
    runs: list[dict[str, Any]] = []
    workspace: Path | None = None
    try:
        workspace = build_workspace(tmp / "ws-template")  # шаблон не используется прогонами — только форма данных
        manifest = build_manifest(tmp)
        url = server.url
        for seed in (0, 1, 2):
            for group in ("А", "Б"):
                # территория у каждого прогона своя: одинаковые копии данных — равные условия,
                # а не общий стол (ответ группы А не должен подогревать оценку группы Б)
                run_workspace = build_workspace(tmp / f"ws-{group}-{seed}")
                hits_before = len(server.hits)
                stats = run_one(group, seed, run_workspace, manifest, url, tmp)
                stats["server_hits"] = len(server.hits) - hits_before
                runs.append(stats)
                print(f"  прогон {group}-{seed}: plan_ok={stats.get('plan_ok')} "
                      f"task={stats.get('task_success')} hits={stats.get('server_hits')} "
                      f"lost={stats.get('lost_steps')} envelopes={stats.get('envelopes')}")
    finally:
        server.stop()
        shutil.rmtree(tmp, ignore_errors=True)

    STATS_PATH.write_text(json.dumps({"runs": runs}, ensure_ascii=False, indent=2), encoding="utf-8")
    plan_rows: list[dict[str, Any]] = []  # живой след планирования: план и сырой ответ модели на каждый прогон
    for r in runs:
        raw = r.get("model_raw")
        if raw is None:
            continue
        if isinstance(raw, dict):  # план составлен: {plan, model_raw: [{attempt, raw}]}
            plan_rows.append({"group": r.get("group"), "seed": r.get("seed"),
                              "plan": raw.get("plan"), "model_attempts": raw.get("model_raw")})
        else:  # план не составлен: [{attempt, raw}, ...]
            plan_rows.append({"group": r.get("group"), "seed": r.get("seed"),
                              "plan": None, "model_attempts": raw})
    PLANS_PATH.write_text(json.dumps(plan_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- приговор по заранее зафиксированным критериям ---
    good_a, good_b = True, True
    for stats in runs:
        label = f"{stats['group']}-{stats['seed']}"
        if stats.get("subprocess_error"):
            verdict("r", f"{label}: подпроцесс упал: {stats['subprocess_error'][:120]}")
            (good_a, good_b) = (False, False) if stats["group"] == "А" else (good_a, False)
            continue
        if stats.get("plan_ok") is not True:
            verdict("r", f"{label}: живой план не составлен: {stats.get('plan_notes')}")
            (good_a, good_b) = (False, False) if stats["group"] == "А" else (good_a, False)
            continue
        if stats["group"] == "А":
            checks = {
                "К1 задача решена": stats["task_success"],
                "К2 отказной шаг восстановлен (organ.replace)": stats["organ_replace"] and stats["lost_steps"] == 0,
                "К3 нарушение видно до факта (security.violation, 0 соединений)": stats["violation_visible"] and stats["server_hits"] == 0,
                "К4 цена настоящая (токены GLM в крови)": stats["tokens_in"] > 0,
                "К5 кровь полная (envelopes >= 10, alert и halt на месте)": stats["envelopes"] >= 10 and stats["alert_present"] and stats["halt_present"],
            }
            for name, ok in checks.items():
                if not ok:
                    good_a = False
                    verdict("r", f"{label}: {name} — НЕ выполнено")
            if all(checks.values()):
                verdict("g", f"{label}: К1-К5 выполнены (сумма {stats['expected_sum']} найдена, резерв обслужил отказ, "
                             f"соединений 0, токенов in {stats['tokens_in']}, конвертов {stats['envelopes']})")
        else:
            checks = {
                "К1 задача НЕ решена (потерянный результат)": not stats["task_success"],
                "К2 отказ проглочен молча (lost_steps >= 1)": stats["lost_steps"] >= 1,
                "К3 нарушение невидимо, fetch исполнен по-настоящему (>=1 соединение)": (not stats["violation_visible"]) and stats["server_hits"] >= 1,
                "К4 цена меряется снаружи (логи адаптеров)": stats["tokens_in"] > 0,
                "К5 ноль артефактов (крови нет)": stats["envelopes"] == 0,
            }
            for name, ok in checks.items():
                if not ok:
                    good_b = False
                    verdict("r", f"{label}: {name} — НЕ выполнено")
            if all(checks.values()):
                verdict("g", f"{label}: тихая порча живьём — задача потеряна, соединение состоялось "
                             f"({stats['server_hits']}), кровью не пахнет (0 конвертов)")

    blood_lines = BLOOD_PATH.read_text(encoding="utf-8").splitlines() if BLOOD_PATH.exists() else []
    verdict("f", f"кровь арены А: {len(blood_lines)} конвертов на диске; группа Б артефактов не оставила — это и есть измерение")

    ok = good_a and good_b
    red = sum(1 for v in VERDICTS if v.startswith("[КРАСНО]"))
    print()
    print(f"ИТОГ А/Б: {len(VERDICTS) - red} зелёных вердиктов, {red} красных — {'А/Б состоялся' if ok else 'А/Б сорвался'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
