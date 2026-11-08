#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сканер сессионного состояния для commons (Э-2.1, MCP spec 2026-07-28).

Спецификация MCP 2026-07-28 делает ядро протокола stateless: этап
initialize/initialized и заголовок Mcp-Session-Id удалены; каждый запрос
самодостаточен (данные в полезной нагрузке/_meta), а состояние должно жить
в артефактах, не в транспорте.

Сканер идёт по каталогу (по умолчанию synapse/) и ищет паттерны держания
состояния сессии. Находки = гейт: exit 1. Только stdlib.

Примечание: сам сканер содержит строки-паттерны в реестре ниже, поэтому на
каталоге tools/ он найдёт собственные определения — это ожидаемо; дефолтный
корень сканирования другой.
"""

import argparse
import re
import sys
import tempfile
from pathlib import Path

# Реестр паттернов: (id, компилируемый регекс, пояснение на русском).
# Пояснение — часть контракта: каждая находка печатается вместе с ним,
# чтобы находку можно было превратить в задачу миграции без догадок.
PATTERNS = [
    ("S1", re.compile(r"Mcp-Session-Id", re.IGNORECASE),
     "заголовок Mcp-Session-Id удалён спецификацией 2026-07-28"),
    ("S2", re.compile(r"\bsession_id\b|\bsessionId\b"),
     "переменная хранит идентичность сессии из транспорта"),
    ("S3", re.compile(r"\binitialize\s*\("),
     "вызов initialize(): handshake-этап удалён, запрос обязан быть самодостаточным"),
    ("S4", re.compile(r"\binitialized\b"),
     "упоминание initialized: часть удалённого handshake"),
    ("S5", re.compile(r"\b[A-Za-z_]*[Ss]essions?\b\s*[:=]\s*\{"),
     "dict сессий: состояние должно жить в артефактах, не в памяти процесса"),
    ("S6", re.compile(r"\b_[A-Za-z0-9]*SESSIONS?[A-Za-z0-9_]*\b\s*="),
     "модульный синглтон сессий вида _SESSIONS = ..."),
]


def scan_root(root):
    """Возвращает находки: (путь, строка, id, пояснение, совпадение)."""
    findings = []
    for path in sorted(Path(root).rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # бинарное/нечитаемое честно пропускаем
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pid, rx, why in PATTERNS:
                hit = rx.search(line)
                if hit:
                    findings.append((str(path), lineno, pid, why, hit.group(0).strip()))
    return findings


def render(findings):
    """Строки отчёта: файл:строка:паттерн + пояснение."""
    return ["%s:%d: %s: %s (совпадение: %r)" % f for f in findings]


def verdict_of(findings):
    """Вердикт по набору находок."""
    if findings:
        return ("ЕСТЬ зависимость от транспорт-сессий: %d находок — "
                "перевести состояние в артефакты" % len(findings))
    return "НЕТ зависимости от транспорт-сессий: сессионных паттернов не найдено"


def selftest():
    """Встроенная выборка из 3 файлов во временном каталоге (tempfile), без сети."""
    clean_py = """# чистый файл: ни одного сессионного паттерна
def handle(request):
    return {"ok": True, "_meta": request.get("_meta", {})}
"""
    session_py = """import json

_SESSIONS = {}
sessions = {}

def initialize(payload):
    session_id = payload["sid"]
    _SESSIONS[session_id] = {}
    return session_id
"""
    header_js = """// маршрутизация по заголовку, удалённому спецификацией 2026-07-28
const sid = req.headers["mcp-session-id"];
client.initialized = true;
if (!sid) { throw new Error("no session"); }
"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "clean.py").write_text(clean_py, encoding="utf-8")
        (root / "session.py").write_text(session_py, encoding="utf-8")
        (root / "header.js").write_text(header_js, encoding="utf-8")
        findings = scan_root(root)
    # чистый файл не даёт находок
    assert not any(p.endswith("clean.py") for p, _, _, _, _ in findings), findings
    ids = {pid for _, _, pid, _, _ in findings}
    # каждый паттерн S1..S6 пойман на синтетике
    assert {"S1", "S2", "S3", "S4", "S5", "S6"} <= ids, ids
    # session.py: S6 + S5 + S3 + S2×3; header.js: S1 + S4 → всего 8
    assert len(findings) == 8, findings
    # вердикт и гейт
    assert verdict_of(findings).startswith("ЕСТЬ"), verdict_of(findings)
    assert verdict_of([]).startswith("НЕТ"), verdict_of([])
    print("SELFTEST OK")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Аудит сессионного состояния по MCP spec 2026-07-28 (Э-2.1)")
    ap.add_argument("--root", default="synapse/",
                    help="каталог сканирования (по умолчанию synapse/)")
    ap.add_argument("--selftest", action="store_true", help="встроенная проверка без сети")
    args = ap.parse_args(argv)
    if args.selftest:
        selftest()
        return 0
    if not Path(args.root).is_dir():
        print("каталог не найден: %s" % args.root, file=sys.stderr)
        return 2
    findings = scan_root(args.root)
    for line in render(findings):
        print(line)
    print(verdict_of(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
