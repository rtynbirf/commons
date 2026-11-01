#!/usr/bin/env python3
"""Спайк S3: оркестрация — n8n против Dify против langflow (docs/spikes.md).

Честная проба трёх low-code платформ по их HTTP-эндпоинтам и измерение «что
видит кровь»: может ли внешний наблюдатель реконструировать трейс с ценами
в форме SPEC-0003. Покрытие полей конверта считается по машинному ответу как
по кандидату в трейс; набор обязательных полей читается из
blood/envelope.schema.json — без хардкода.

Запуск:
  python3 spikes/s3-orchestration/measure.py --matrix   # офлайн: лицензионная матрица
  S3_N8N_URL=http://127.0.0.1:5678 S3_DIFY_URL=... S3_LANGFLOW_URL=... \
  python3 spikes/s3-orchestration/measure.py --probe    # проба живых эндпоинтов
Без флагов: есть S3_*_URL — как --probe, нет — NO_SERVER.

Ключи S3_N8N_KEY / S3_DIFY_KEY / S3_LANGFLOW_KEY уходят в заголовки
Authorization/X-API-Key и никогда не печатаются. Без серверов печатает
NO_SERVER (код 2) — цифры не выдумываются. Только стандартная библиотека.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # spikes/s3-orchestration/measure.py → корень репо
SCHEMA_PATH = REPO_ROOT / "blood" / "envelope.schema.json"

HEALTH_PATHS = ("/healthz", "/health", "/")
TIMEOUT = 10.0  # секунды на один запрос
BODY_LIMIT = 65536  # байт: пробе достаточно начала тела ответа


def _load_required_fields() -> tuple[str, ...]:
    """Обязательные поля конверта SPEC-0003 — из схемы крови, не из головы."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return tuple(schema["required"])


REQUIRED_FIELDS: tuple[str, ...] = _load_required_fields()

# Лицензионная матрица: захардкожена, верифицирована GitHub API
# (GET /repos/{owner}/{repo}/license, 2026-11-02). NOASSERTION — «GitHub не
# распознал автоматически», не «нет лицензии» (расшифровка — PROVENANCE.md §3).
LICENSE_MATRIX = (
    ("langchain-ai/langchain", "MIT", "dependency — орган, не ствол мозга (спайк S2)"),
    ("langflow-ai/langflow", "MIT", "reference — изучение"),
    ("langgenius/dify", "NOASSERTION → Apache-2.0 с доп. условиями", "adapter (условно)"),
    ("n8n-io/n8n", "NOASSERTION → fair-code (Sustainable Use)", "external, не встраивается"),
)

# Платформы пробы: URL и ключ берутся из окружения; ключ не печатается никогда.
PLATFORMS = (
    {"name": "n8n", "url_env": "S3_N8N_URL", "key_env": "S3_N8N_KEY"},
    {"name": "Dify", "url_env": "S3_DIFY_URL", "key_env": "S3_DIFY_KEY"},
    {"name": "langflow", "url_env": "S3_LANGFLOW_URL", "key_env": "S3_LANGFLOW_KEY"},
)


def trace_coverage(trace: dict) -> tuple[int, list[str]]:
    """Покрытие конверта SPEC-0003: (сколько обязательных полей есть, каких не хватает).

    Набор полей берётся из blood/envelope.schema.json (REQUIRED_FIELDS),
    список отсутствующих возвращается отсортированным.
    """
    missing = sorted(field for field in REQUIRED_FIELDS if field not in trace)
    return len(REQUIRED_FIELDS) - len(missing), missing


def _headers(key: str | None) -> dict[str, str]:
    """Заголовки запроса; значение ключа попадает сюда, но не в вывод."""
    headers = {"User-Agent": "commons-spike-s3"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
        headers["X-API-Key"] = key
    return headers


def _fetch(url: str, key: str | None) -> tuple[float, int, dict, bytes] | None:
    """Один GET: (latency, код, заголовки, тело). 4xx/5xx — тоже ответ машины; None — связи нет."""
    request = urllib.request.Request(url, headers=_headers(key), method="GET")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return time.monotonic() - started, response.status, dict(response.headers), response.read(BODY_LIMIT)
    except urllib.error.HTTPError as error:  # машина ответила — фиксируем честно, с кодом ошибки
        return time.monotonic() - started, error.code, dict(error.headers or {}), error.read(BODY_LIMIT)
    except (urllib.error.URLError, TimeoutError, OSError):  # refused / dns / таймаут
        return None


def _candidate_trace(headers: dict, body: bytes) -> dict:
    """Всё машинно-видимое из ответа — кандидат в трейс (честно: обычно мимо SPEC-0003)."""
    candidate = {str(name): str(value) for name, value in headers.items()}
    try:
        parsed = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return candidate
    if isinstance(parsed, dict):
        candidate.update(parsed)  # тело ответа тоже видимо внешнему наблюдателю
    return candidate


def probe_platform(name: str, base_url: str, key: str | None) -> dict:
    """Перебирает health-пути; возвращает строку пробы или честное «недоступна»."""
    fallback: tuple[str, float, int, dict, bytes] | None = None
    for path in HEALTH_PATHS:
        fetched = _fetch(base_url.rstrip("/") + path, key)
        if fetched is None:
            continue
        latency, code, headers, body = fetched
        present, missing = trace_coverage(_candidate_trace(headers, body))
        if 200 <= code < 300:
            return {"name": name, "alive": True, "latency": round(latency, 3),
                    "http": f"{code} ({path})", "present": present, "missing": missing}
        if fallback is None:  # живой ответ с ошибкой — запас, если 2xx нигде нет
            fallback = (path, latency, code, headers, body)
    if fallback is None:
        return {"name": name, "alive": False, "latency": None, "http": "недоступна",
                "present": None, "missing": []}
    path, latency, code, headers, body = fallback
    present, missing = trace_coverage(_candidate_trace(headers, body))
    return {"name": name, "alive": True, "latency": round(latency, 3),
            "http": f"{code} ({path}, не 2xx)", "present": present, "missing": missing}


def print_license_matrix() -> None:
    """Офлайн-матрица: лицензии верифицированы, замеры «что отдаёт наружу» — прочерки."""
    print("Лицензионная матрица спайка S3 — верифицирована GitHub API 2026-11-02")
    print("(GET /repos/{owner}/{repo}/license); NOASSERTION — см. PROVENANCE.md §3.")
    print()
    print("| платформа | SPDX | режим в теле | что отдаёт наружу |")
    print("| --- | --- | --- | --- |")
    for repo, spdx, mode in LICENSE_MATRIX:
        print(f"| {repo} | {spdx} | {mode} | — |")
    print()
    print("Прочерк в «что отдаёт наружу» — замер не проводился: --matrix офлайн,")
    print("живая проба эндпоинтов — --probe (S3_N8N_URL / S3_DIFY_URL / S3_LANGFLOW_URL).")


def print_probe_table(rows: list[dict]) -> None:
    """Итог пробы: платформа | latency | HTTP | покрытие SPEC-0003 | отсутствуют."""
    print(f"Проба живых эндпоинтов (health-пути: {', '.join(HEALTH_PATHS)}; таймаут {TIMEOUT:.0f} с):")
    print()
    print("| платформа | latency, с | HTTP | полей SPEC-0003 | отсутствуют |")
    print("| --- | --- | --- | --- | --- |")
    for row in rows:
        if not row["alive"]:
            print(f"| {row['name']} | — | недоступна | — | — |")
            continue
        missing = ", ".join(row["missing"]) if row["missing"] else "—"
        print(f"| {row['name']} | {row['latency']} | {row['http']}"
              f" | {row['present']}/{len(REQUIRED_FIELDS)} | {missing} |")


def cmd_probe() -> int:
    """Проба живых эндпоинтов; 0 — кто-то ответил, 2 — нечего мерить."""
    targets = [(platform["name"], os.environ.get(platform["url_env"]), os.environ.get(platform["key_env"]))
               for platform in PLATFORMS]
    if not any(url for _, url, _ in targets):
        print("NO_SERVER: ни один эндпоинт не задан — спайк не врёт вместо замера.")
        print("Подсказка: S3_N8N_URL / S3_DIFY_URL / S3_LANGFLOW_URL задают эндпоинты,")
        print("S3_*_KEY — ключи (уходят в заголовки, не печатаются).")
        return 2

    rows = [probe_platform(name, url, key) for name, url, key in targets if url]
    print_probe_table(rows)
    if not any(row["alive"] for row in rows):
        print()
        print("NO_SERVER: заданные эндпоинты не ответили — спайк не врёт вместо замера.")
        return 2

    alive = [row for row in rows if row["alive"]]
    print()
    if all(row["present"] == 0 for row in alive):
        print(f"Ни одна ответившая платформа не отдала ни одного из {len(REQUIRED_FIELDS)}")
        print("полей SPEC-0003 — гипотеза «платформа не отдаёт трейс с ценами» подтверждается на пробе.")
    print("Вердикт — в spikes/s3-orchestration/README.md (docs/spikes.md, S3).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Спайк S3: оркестрация — n8n против Dify против langflow")
    parser.add_argument("--matrix", action="store_true", help="офлайн: верифицированная лицензионная матрица")
    parser.add_argument("--probe", action="store_true", help="проба живых эндпоинтов из S3_*_URL")
    args = parser.parse_args()
    if args.matrix:
        print_license_matrix()
        return 0
    return cmd_probe()


if __name__ == "__main__":
    raise SystemExit(main())
