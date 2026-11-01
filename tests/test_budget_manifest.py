"""Приёмка M3 SPEC-0001 G3: бюджеты органов читаются из манифеста.

Лимит живёт с органом в манифесте, не в коде: правка YAML, не правка ствола
мозга (brainstem.budget.budgets_from_manifest). Повреждённый бюджет —
GatewayConfigError: манифест не валиден, организм не стартует.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from brainstem.budget import budgets_from_manifest
from brainstem.loop import Budget
from synapse.gateway import GatewayConfigError

REPO = pathlib.Path(__file__).resolve().parents[1]


def write_manifest(tmp_path: pathlib.Path, raw: object) -> pathlib.Path:
    """Пишет временный манифест: raw — python-объект (safe_dump) или готовый YAML-текст."""
    path = tmp_path / "mcp-manifest.yaml"
    if isinstance(raw, str):
        path.write_text(raw, encoding="utf-8")
    else:
        path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return path


def organ(name: str, **extra: object) -> dict:
    """Минимальная запись органа: парсеру бюджета нужны только name/budget."""
    return {"name": name, **extra}


# --- приёмка 1-2: валидный бюджет читается в Budget ---


def test_full_budget_from_manifest(tmp_path: pathlib.Path) -> None:
    """Бюджет одного из двух органов -> одна запись; поля Budget совпадают, alert_ratio 0.8."""
    manifest = {
        "organs": [
            organ("ollama", budget={"tokens_in": 100, "tokens_out": 50, "seconds": 30}),
            organ("markitdown"),  # без budget — в результат не попадает
        ]
    }
    budgets = budgets_from_manifest(write_manifest(tmp_path, manifest))
    assert set(budgets) == {"ollama"}
    assert budgets["ollama"] == Budget(tokens_in=100, tokens_out=50, seconds=30)
    assert budgets["ollama"].alert_ratio == 0.8  # дефолт из brainstem.loop.Budget


def test_fractional_seconds_and_alert_ratio(tmp_path: pathlib.Path) -> None:
    """seconds — дробь, alert_ratio перекрывает дефолт, токены остаются None."""
    manifest = {"organs": [organ("browser-use", budget={"seconds": 12.5, "alert_ratio": 0.5})]}
    budgets = budgets_from_manifest(write_manifest(tmp_path, manifest))
    budget = budgets["browser-use"]
    assert budget.tokens_in is None and budget.tokens_out is None
    assert budget == Budget(seconds=12.5, alert_ratio=0.5)


# --- приёмка 3: живой манифест репо ---


def test_live_manifest_has_no_budgets() -> None:
    """Живой манифест репо пока без поля budget: результат пуст — лимит не задан, норма."""
    assert budgets_from_manifest(REPO / "synapse" / "mcp-manifest.yaml") == {}


# --- приёмка 4: битые бюджеты -> GatewayConfigError с русским текстом ---


@pytest.mark.parametrize(
    ("budget", "message"),
    [
        ("всё и сразу", "манифест: ollama: поле budget не словарь"),
        ({"запас": 10}, "манифест: ollama: неизвестный ключ бюджета 'запас'"),
        ({"tokens_in": 0}, "манифест: ollama: tokens_in должен быть положительным целым"),
        ({"tokens_in": -5}, "манифест: ollama: tokens_in должен быть положительным целым"),
        ({"tokens_in": 3.5}, "манифест: ollama: tokens_in должен быть положительным целым"),
        ({"tokens_in": True}, "манифест: ollama: tokens_in должен быть положительным целым"),
        ({"seconds": 0}, "манифест: ollama: seconds должен быть положительным числом"),
        ({"seconds": -1}, "манифест: ollama: seconds должен быть положительным числом"),
        ({"seconds": "много"}, "манифест: ollama: seconds должен быть положительным числом"),
        ({"alert_ratio": 0}, "манифест: ollama: alert_ratio должен быть числом из (0, 1]"),
        ({"alert_ratio": 1.5}, "манифест: ollama: alert_ratio должен быть числом из (0, 1]"),
        ({"alert_ratio": "высокий"}, "манифест: ollama: alert_ratio должен быть числом из (0, 1]"),
    ],
)
def test_broken_budget_rejected(tmp_path: pathlib.Path, budget: object, message: str) -> None:
    """Повреждённый бюджет — GatewayConfigError с точным русским текстом."""
    path = write_manifest(tmp_path, {"organs": [organ("ollama", budget=budget)]})
    with pytest.raises(GatewayConfigError) as excinfo:
        budgets_from_manifest(path)
    assert str(excinfo.value) == message


# --- приёмка 5: манифест не словарь / без organs ---


def test_manifest_without_organs_rejected(tmp_path: pathlib.Path) -> None:
    """Манифест без списка organs — шлюз не стартует."""
    path = write_manifest(tmp_path, {"version": "0.0.1"})
    with pytest.raises(GatewayConfigError) as excinfo:
        budgets_from_manifest(path)
    assert str(excinfo.value) == "манифест: отсутствует список organs"


def test_non_dict_manifest_rejected(tmp_path: pathlib.Path) -> None:
    """YAML-файл без словаря (список вместо отображения) — тот же отказ."""
    path = write_manifest(tmp_path, "- просто список\n")
    with pytest.raises(GatewayConfigError) as excinfo:
        budgets_from_manifest(path)
    assert str(excinfo.value) == "манифест: отсутствует список organs"


# --- приёмка 6: запись без имени ---


@pytest.mark.parametrize(
    "entry",
    [
        {"budget": {"seconds": 1}},  # словарь с бюджетом, но без name
        "голая строка",  # запись вообще не словарь
    ],
)
def test_entry_without_name_rejected(tmp_path: pathlib.Path, entry: object) -> None:
    """Запись organs без name (или не словарь) — GatewayConfigError("запись без имени")."""
    path = write_manifest(tmp_path, {"organs": [organ("живой"), entry]})
    with pytest.raises(GatewayConfigError) as excinfo:
        budgets_from_manifest(path)
    assert str(excinfo.value) == "манифест: запись без имени"
