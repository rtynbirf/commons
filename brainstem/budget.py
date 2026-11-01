# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Бюджеты органов из манифеста — SPEC-0001 G3 (M3): декларативные лимиты метаболизма.

Лимит живёт с органом в манифесте, не в коде (дух G2 SPEC-0001): правка YAML,
не правка ствола мозга. Повреждённый бюджет — манифест не валиден (GatewayConfigError).
"""
from __future__ import annotations

import pathlib
from typing import Any

import yaml

from brainstem.loop import Budget
from synapse.gateway import GatewayConfigError

_ALLOWED_KEYS = {"tokens_in", "tokens_out", "seconds", "alert_ratio"}


def budgets_from_manifest(manifest_path: str | pathlib.Path) -> dict[str, Budget]:
    """Читает поле budget каждого органа манифеста -> {имя: Budget}.

    Правила (все нарушения -> GatewayConfigError, русский текст):
    - файл не dict / без списка organs -> GatewayConfigError("манифест: отсутствует список organs")
    - запись не dict или без name -> GatewayConfigError("манифест: запись без имени")
    - budget отсутствует -> органа в результате нет (лимит не задан — норма)
    - budget не dict -> GatewayConfigError("манифест: {name}: поле budget не словарь")
    - ключ не из _ALLOWED_KEYS -> GatewayConfigError("манифест: {name}: неизвестный ключ бюджета {key!r}")
    - tokens_in/tokens_out: строго положительный int (bool не считается!) иначе
      GatewayConfigError("манифест: {name}: {key} должен быть положительным целым")
    - seconds: строго положительное int/float (не bool) иначе
      GatewayConfigError("манифест: {name}: seconds должен быть положительным числом")
    - alert_ratio: опционален; float/int (не bool) в (0, 1] иначе
      GatewayConfigError("манифест: {name}: alert_ratio должен быть числом из (0, 1]")
    Возвращает словарь только для органов с валидным бюджетом.
    """
    raw = yaml.safe_load(pathlib.Path(manifest_path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("organs"), list):
        raise GatewayConfigError("манифест: отсутствует список organs")

    budgets: dict[str, Budget] = {}
    for entry in raw["organs"]:
        if not isinstance(entry, dict) or "name" not in entry:
            raise GatewayConfigError("манифест: запись без имени")
        name = entry["name"]
        if "budget" not in entry:
            continue  # лимит не задан — норма, орган просто без бюджета
        if not isinstance(entry["budget"], dict):
            raise GatewayConfigError(f"манифест: {name}: поле budget не словарь")
        budgets[name] = _budget_from(entry["budget"], name)
    return budgets


def _budget_from(raw: dict[str, Any], name: str) -> Budget:
    """Валидирует распарсенный бюджет одного органа и собирает Budget (G3)."""
    fields: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in _ALLOWED_KEYS:
            raise GatewayConfigError(f"манифест: {name}: неизвестный ключ бюджета {key!r}")
        if key in ("tokens_in", "tokens_out"):
            # bool — подкласс int, но true как лимит токенов бессмысленен.
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise GatewayConfigError(f"манифест: {name}: {key} должен быть положительным целым")
        elif key == "seconds":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise GatewayConfigError(f"манифест: {name}: seconds должен быть положительным числом")
        else:  # alert_ratio: доля лимита, на которой бьёт алерт
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 1:
                raise GatewayConfigError(f"манифест: {name}: alert_ratio должен быть числом из (0, 1]")
        fields[key] = value
    return Budget(**fields)
