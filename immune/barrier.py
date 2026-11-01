# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Лицензионный барьер COMMONS (SPEC-0006): пара (license, mode) -> вердикт.

Иммунитет — фильтр на входе органа в тело. Матрица правил — данные
(immune/license-matrix.yaml, G2); этот модуль — только механизм применения.
Fail-closed (G1): лицензия, не описанная матрицей, запрещена во встраивание.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
from collections.abc import Iterable
from dataclasses import dataclass

import yaml

MATRIX_PATH = pathlib.Path(__file__).with_name("license-matrix.yaml")

# Пути гейта по умолчанию (относительно cwd; см. main()).
DEFAULT_PATHS = ("synapse/mcp-manifest.yaml", "organs/registry.yaml")

# sys.stdout на момент импорта — фактический объект-дефолт параметра out
# (см. run_check: дефолт пере-разрешается в момент вызова).
_IMPORT_STDOUT = sys.stdout


@dataclass(frozen=True)
class Decision:
    """Вердикт барьера по одному органу."""

    ok: bool
    license: str
    mode: str
    rule: str          # имя применимого правила матрицы (allowed/conditional/restricted/unrecognized/fail-closed/unknown-mode/missing)
    reason: str        # человекочитаемая причина на русском
    organ: str = ""


def _blank(value: object) -> bool:
    """Поле пусто для барьера: None, не строка или одни пробелы."""
    return not isinstance(value, str) or not value.strip()


def load_matrix(path: pathlib.Path | None = None) -> dict:
    """Матрица из данных; path=None -> пакетная license-matrix.yaml."""
    p = path if path is not None else MATRIX_PATH
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "core_modes" not in data or "modes" not in data:
        raise ValueError(f"матрица повреждена: {p}")
    return data


def verdict(license: str, mode: str, matrix: dict, organ: str = "") -> Decision:
    """Вердикт для пары (license, mode). Семантика:
    1) mode не из matrix['modes'] -> ok=False, rule='unknown-mode';
    2) license в allowed -> ok=True, rule='allowed';
    3) license в conditional -> ok=True iff mode в списке этой лицензии, rule='conditional';
    4) license в restricted -> ok=False если mode в core_modes, иначе ok=True, rule='restricted';
    5) иначе (неизвестная) -> ok=False если mode в core_modes (G1 fail-closed, rule='fail-closed'),
       иначе ok=True, rule='unrecognized' (вне встраивания — контакт не переносит код);
    6) license или mode отсутствуют/пустые -> ok=False, rule='missing'.

    Проверка (6) выполняется первой: без лицензии или режима остальные правила
    неприменимы. Строки лицензий сверяются с матрицей дословно, без нормализации.
    """
    # (6) отсутствие данных — прежде всех правил.
    if _blank(license) or _blank(mode):
        if _blank(license) and _blank(mode):
            reason = "лицензия и режим не указаны"
        elif _blank(license):
            reason = "лицензия не указана"
        else:
            reason = "режим не указан"
        return Decision(
            ok=False,
            license=license if isinstance(license, str) else "",
            mode=mode if isinstance(mode, str) else "",
            rule="missing",
            reason=reason,
            organ=organ,
        )

    modes: list = matrix.get("modes") or []
    core_modes: list = matrix.get("core_modes") or []
    allowed: list = matrix.get("allowed") or []
    conditional: dict = matrix.get("conditional") or {}
    restricted: list = matrix.get("restricted") or []

    # (1) режим вне матрицы — отказ независимо от лицензии.
    if mode not in modes:
        return Decision(
            ok=False,
            license=license,
            mode=mode,
            rule="unknown-mode",
            reason=f"неизвестный режим '{mode}': матрица знает {', '.join(map(str, modes))}",
            organ=organ,
        )

    # (2) разрешено повсеместно.
    if license in allowed:
        return Decision(
            ok=True,
            license=license,
            mode=mode,
            rule="allowed",
            reason=f"лицензия '{license}' разрешена повсеместно (permissive OSI)",
            organ=organ,
        )

    # (3) условная лицензия: допустима только в перечисленных для неё режимах.
    if license in conditional:
        permitted = conditional[license]
        permitted = permitted if isinstance(permitted, list) else []
        if mode in permitted:
            return Decision(
                ok=True,
                license=license,
                mode=mode,
                rule="conditional",
                reason=f"условная лицензия '{license}' допустима в режиме '{mode}' (разрешено: {', '.join(map(str, permitted))})",
                organ=organ,
            )
        return Decision(
            ok=False,
            license=license,
            mode=mode,
            rule="conditional",
            reason=f"условная лицензия '{license}' недопустима в режиме '{mode}' (разрешено только: {', '.join(map(str, permitted))})",
            organ=organ,
        )

    # (4) ограниченная: запрет только во встраивание в тело (core_modes).
    if license in restricted:
        if mode in core_modes:
            return Decision(
                ok=False,
                license=license,
                mode=mode,
                rule="restricted",
                reason=f"ограниченная лицензия '{license}' не встраивается в тело (режим '{mode}' из core_modes: {', '.join(map(str, core_modes))})",
                organ=organ,
            )
        return Decision(
            ok=True,
            license=license,
            mode=mode,
            rule="restricted",
            reason=f"ограниченная лицензия '{license}' вне встраивания допустима (режим '{mode}' — вне тела)",
            organ=organ,
        )

    # (5) неизвестная лицензия: во встраивании — fail-closed (G1),
    # вне тела — контакт не переносит код и потому терпим.
    if mode in core_modes:
        return Decision(
            ok=False,
            license=license,
            mode=mode,
            rule="fail-closed",
            reason=f"лицензия '{license}' не описана матрицей: во встраивание в тело запрещена (G1 fail-closed)",
            organ=organ,
        )
    return Decision(
        ok=True,
        license=license,
        mode=mode,
        rule="unrecognized",
        reason=f"лицензия '{license}' не описана матрицей: вне тела допустима (контакт не переносит код)",
        organ=organ,
    )


def check_entries(entries: Iterable[dict], matrix: dict, source: str = "") -> list[Decision]:
    """Проверка перечня записей. Запись: dict; имя органа — 'name' или 'repo';
    лицензия — 'license' или 'license_pre'; режим — 'mode'.
    Отсутствие любого из трёх -> Decision(ok=False, rule='missing').

    source — метка происхождения записей (например, путь к файлу); при заданной
    она добавляется к имени органа в Decision.organ как '<source>:<имя>'.
    """
    decisions: list[Decision] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            brief = " ".join(str(entry).split())[:120]
            decisions.append(
                Decision(
                    False, "", "", "missing", "запись органа — не словарь (fail-closed)",
                    organ=f"{source}:{brief}" if source else brief,
                )
            )
            continue

        name = entry.get("name") or entry.get("repo")
        license_ = entry.get("license")
        if _blank(license_):
            license_ = entry.get("license_pre")
        mode = entry.get("mode")

        absent: list[str] = []
        if _blank(name):
            absent.append("имя органа (name/repo)")
        if _blank(license_):
            absent.append("лицензия (license/license_pre)")
        if _blank(mode):
            absent.append("режим (mode)")

        name_s = name if isinstance(name, str) else ""
        organ = f"{source}:{name_s}" if source and name_s else (name_s or source)
        if absent:
            decisions.append(
                Decision(
                    False,
                    license_ if isinstance(license_, str) else "",
                    mode if isinstance(mode, str) else "",
                    "missing",
                    "не указано: " + ", ".join(absent),
                    organ=organ,
                )
            )
            continue
        decisions.append(verdict(license_, mode, matrix, organ=organ))
    return decisions


def run_check(paths: Iterable[str | pathlib.Path], matrix: dict | None = None, out=sys.stdout) -> int:
    """Гейт: проверить YAML-файлы органов; вернуть 0 если все ok, иначе 1.
    Каждый файл: либо dict с ключом 'organs': [...], либо список.
    Вывод: по строке на орган ('OK <organ> <license> <mode> (<rule>)' или
    'FAIL <organ> <license> <mode> (<rule>): <reason>'), в конце итог
    'IMMUNE: N ok, M failed' либо 'IMMUNE: FAIL'. Ошибка чтения/парсинга файла ->
    сообщение + вклад в отказ (fail-closed).

    Уточнение формата: итог печатается дословно — при успехе
    'IMMUNE: N ok, M failed' (M = 0), при отказах 'IMMUNE: FAIL (N ok, M failed)'.
    Орган в строке именуется '<source>:<имя>' (source = путь файла). Любая
    структура файла вне двух описанных форм — отказ файла целиком. Дефолт out
    разрешается в момент вызова: под pytest (capsys) актуальный sys.stdout
    подменяется после импорта модуля.
    """
    if out is _IMPORT_STDOUT:
        out = sys.stdout
    if matrix is None:
        matrix = load_matrix()

    ok_count = 0
    failed = 0
    for raw in paths:
        path = pathlib.Path(raw)
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, yaml.YAMLError) as exc:
            failed += 1
            print(f"FAIL {path}: файл не прочитан или не разобран: {exc}", file=out)
            continue
        if isinstance(data, dict) and isinstance(data.get("organs"), list):
            entries = data["organs"]
        elif isinstance(data, list):
            entries = data
        else:
            failed += 1
            print(f"FAIL {path}: ожидается dict с ключом 'organs' (список) или список органов", file=out)
            continue
        for decision in check_entries(entries, matrix, source=str(path)):
            if decision.ok:
                ok_count += 1
                print(f"OK {decision.organ} {decision.license} {decision.mode} ({decision.rule})", file=out)
            else:
                failed += 1
                print(f"FAIL {decision.organ} {decision.license} {decision.mode} ({decision.rule}): {decision.reason}", file=out)

    if failed:
        print(f"IMMUNE: FAIL ({ok_count} ok, {failed} failed)", file=out)
        return 1
    print(f"IMMUNE: {ok_count} ok, {failed} failed", file=out)
    return 0


def main(argv=None) -> int:
    """CLI: python -m immune [--matrix PATH] [paths...]
    Пути по умолчанию: synapse/mcp-manifest.yaml, organs/registry.yaml (относительно cwd)."""
    parser = argparse.ArgumentParser(
        prog="python -m immune",
        description="Лицензионный барьер COMMONS (SPEC-0006): проверка пар (license, mode) органов по матрице.",
    )
    parser.add_argument(
        "--matrix", type=pathlib.Path, default=None,
        help="путь к матрице правил (по умолчанию — пакетная license-matrix.yaml)",
    )
    parser.add_argument(
        "paths", nargs="*",
        help="YAML-файлы органов: dict с ключом 'organs' или список (по умолчанию: "
             + ", ".join(DEFAULT_PATHS) + ")",
    )
    args = parser.parse_args(argv)

    try:
        matrix = load_matrix(args.matrix)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"IMMUNE: FAIL: матрица не загружена: {exc}", file=sys.stderr)
        return 1

    return run_check(list(args.paths) or list(DEFAULT_PATHS), matrix=matrix)
