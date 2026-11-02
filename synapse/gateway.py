"""MCP-шлюз — SPEC-0002.

Правила шлюза:
1. Источник истины — `synapse/mcp-manifest.yaml`; манифест не валиден — шлюз не стартует.
2. Орган или инструмент без записи в манифесте → событие `veto`.
3. Неотвечающий орган уходит к замене из таблицы `substitutions` (`organ.replace`).
4. Адаптер органа загружается по полю `adapter` манифеста: новый орган подключается
   правкой манифеста, без правки кода шлюза (приёмка SPEC-0002).
5. Каждый вызов попадает в кровь как `act` с заполненной ценой.
6. Полномочия исполняются рантаймом (SPEC-0002 п.8): на время invoke активен страж
   (synapse.authority) — выход за заявленное прерывается `AuthorityViolation`, кровь
   помнит `security.violation`; грамматика authority проверяется при старте шлюза.
7. Адаптер обязан предъявлять запись манифеста (SPEC-0002 п.9): самозванец и
   безымянный отклоняются при привязке — до любого вызова.
"""

from __future__ import annotations

import importlib
import os
import re
import time
from pathlib import Path
from typing import Any

import yaml

from blood.envelope import Cost, make
from blood.journal import Journal
from synapse.authority import AuthorityConfigError, AuthorityViolation, enforce, normalize as normalize_authority

REQUIRED_FIELDS = {"name", "system", "mode", "upstream", "license", "transport", "tools", "authority"}
TRANSPORT_REQUIREMENTS = {"stdio": {"command"}, "http": {"endpoint"}}
_PLACEHOLDER = re.compile(r"\$\{([^}]+)\}")


class GatewayConfigError(RuntimeError):
    """Манифест не валиден — шлюз не стартует (SPEC-0002)."""


class SynapseVeto(RuntimeError):
    """Вызов не прошёл через манифест: орган или инструмент не объявлены."""


class OrganUnavailable(RuntimeError):
    """Орган и все его замены недоступны."""


# AuthorityViolation живёт в synapse.authority и ре-экспортируется здесь:
# `from synapse.gateway import AuthorityViolation` продолжает работать (обратная совместимость),
# а except в call() ловит и нарушения стража, и заявления адаптера — класс один.


class Gateway:
    """Шлюз синапсов: единственный способ дотянуться до органа."""

    def __init__(self, manifest_path: str | Path, journal: Journal | None = None) -> None:
        self.journal = journal
        path = Path(manifest_path)
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("organs"), list):
            raise GatewayConfigError("манифест: отсутствует список organs")

        self._organs: dict[str, dict[str, Any]] = {}
        undeployed_authority: set[str] = set()
        for entry in raw["organs"]:
            if not isinstance(entry, dict) or not REQUIRED_FIELDS.issubset(entry):
                missing = REQUIRED_FIELDS - set(entry or {})
                raise GatewayConfigError(f"манифест: запись без полей {sorted(missing)}")
            name = entry["name"]
            if name in self._organs:
                raise GatewayConfigError(f"манифест: две записи с именем {name!r}")
            transport = entry["transport"]
            if transport not in TRANSPORT_REQUIREMENTS:
                raise GatewayConfigError(f"манифест: {name}: неизвестный транспорт {transport!r}")
            absent = TRANSPORT_REQUIREMENTS[transport] - set(entry)
            if absent:
                raise GatewayConfigError(f"манифест: {name}: для транспорта {transport} нужны {sorted(absent)}")
            if not isinstance(entry["tools"], list) or not entry["tools"]:
                raise GatewayConfigError(f"манифест: {name}: список tools пуст или не список")
            unresolved = self._unresolved(name, entry)
            if unresolved:
                # SPEC-0002 п.6: адрес/команда или authority-путь не развёрнуты — орган не получает
                # трафика, но запись в манифесте жива (veto-семантика и замены как раньше).
                if unresolved.endswith(".authority"):
                    undeployed_authority.add(name)  # v0.5.0: скоуп не развернулся — страж не стартует, адаптера нет
                self._organs[name] = entry
                continue
            for field in ("endpoint", "command"):
                if field in entry:
                    entry[field] = self._expand_env(entry[field])
            entry["authority"] = self._expand_env(entry.get("authority"))
            try:
                entry["authority"] = normalize_authority(entry["authority"])
            except AuthorityConfigError as exc:
                raise GatewayConfigError(f"манифест: {name}: authority: {exc}") from exc  # SPEC-0002 п.8: грамматика исполнима
            self._organs[name] = entry

        subs = raw.get("substitutions") or {}
        self._substitutions: dict[str, list[str]] = {str(k): list(v) for k, v in subs.items()}
        for organ, reserves in self._substitutions.items():
            unknown = [r for r in reserves if r not in self._organs]
            if unknown:
                raise GatewayConfigError(f"манифест: замены для {organ} ссылаются на неизвестные органы {unknown}")

        self._adapters: dict[str, Any] = {}
        for name, entry in self._organs.items():
            if name in undeployed_authority:
                continue  # орган не развёрнут (п.6): страж не может получить свои полномочия — адаптера нет
            dotted = entry.get("adapter")
            if dotted:
                adapter = self._instantiate_adapter(dotted, entry)
                self._require_identity(name, adapter)  # SPEC-0002 п.9
                self._adapters[name] = adapter

    # --- сборка адаптера из манифеста (приёмка SPEC-0002: без кода шлюза) ---

    @staticmethod
    def _unresolved(name: str, entry: dict[str, Any]) -> str | None:
        """SPEC-0002 п.6: незаданная ${VAR} в endpoint/command/authority = орган не развёрнут (v0.5.0: и в путях скоупов)."""
        for field in ("endpoint", "command"):
            value = entry.get(field)
            items = value if isinstance(value, list) else [value]
            for item in items:
                if isinstance(item, str) and any(var not in os.environ for var in _PLACEHOLDER.findall(item)):
                    return f"{name}.{field}"
        for item in Gateway._strings(entry.get("authority")):
            if any(var not in os.environ for var in _PLACEHOLDER.findall(item)):
                return f"{name}.authority"
        return None

    @staticmethod
    def _strings(value: Any):
        """Все строки внутри значения (рекурсивно: dict/list/str) — для проверки плейсхолдеров."""
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from Gateway._strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from Gateway._strings(item)

    @staticmethod
    def _expand_env(value: Any) -> Any:
        """Расширяет ${VAR} (переменные гарантированно заданы — см. _unresolved), включая dict/list."""
        if isinstance(value, str):
            return _PLACEHOLDER.sub(lambda m: os.environ[m.group(1)], value)
        if isinstance(value, list):
            return [Gateway._expand_env(item) for item in value]
        if isinstance(value, dict):
            return {key: Gateway._expand_env(item) for key, item in value.items()}
        return value

    @staticmethod
    def _instantiate_adapter(dotted: str, entry: dict[str, Any]) -> Any:
        try:
            module_path, class_name = dotted.split(":")
            cls = getattr(importlib.import_module(module_path), class_name)
        except Exception as exc:  # noqa: BLE001 — ошибка конфигурации всегда
            raise GatewayConfigError(f"адаптер {dotted!r} не загрузился: {exc}") from exc
        return cls(entry)

    def _require_identity(self, organ: str, adapter: Any) -> None:
        """SPEC-0002 п.9: адаптер обязан нести запись манифеста и предъявлять имя органа."""
        entry = getattr(adapter, "entry", None)
        presented = entry.get("name") if isinstance(entry, dict) else None
        if presented != organ:
            if presented is None:
                raise GatewayConfigError(f"адаптер-самозванец: безымянный адаптер (нет entry с именем) не может служить органом {organ!r}")
            raise GatewayConfigError(f"адаптер-самозванец: адаптер предъявляет имя {presented!r}, а привязка идёт к органу {organ!r}")

    def bind_adapter(self, organ: str, adapter: Any) -> None:
        """Явная привязка адаптера (тесты и подмена без правки манифеста)."""
        if organ not in self._organs:
            raise SynapseVeto(f"{organ!r} не существует: нет записи в манифесте")
        self._require_identity(organ, adapter)  # отказ до мутации привязки (SPEC-0002 п.9)
        self._adapters[organ] = adapter

    # --- кровь ---

    def _emit(self, event_type: str, organ: str, payload: dict[str, Any], cost: Cost | None = None, trace_id: str = "-") -> None:
        if self.journal is not None:
            self.journal.append(make(event_type, "synapse", organ, trace_id, payload, cost))

    # --- health ---

    def health(self, organ: str) -> bool:
        adapter = self._adapters.get(organ)
        if adapter is None:
            return False
        try:
            return bool(adapter.health())
        except Exception:  # noqa: BLE001 — не отвечающий орган = нездоров
            return False

    def manifest_entry(self, organ: str) -> dict[str, Any]:
        return dict(self._organs[organ])

    @property
    def organ_names(self) -> list[str]:
        return list(self._organs)

    @property
    def adapters(self) -> list[Any]:
        """Живые адаптеры манифеста — для shutdown() органов при смерти организма (SPEC-0002 п.7)."""
        return list(self._adapters.values())

    # --- вызов ---

    def call(self, organ: str, tool: str, payload: dict[str, Any] | None, trace_id: str, _seen: frozenset[str] = frozenset()) -> Any:
        """Вызов органа через синапс. Любой исход попадает в кровь.

        `_seen` — защита от циклов в таблице замен (SPEC-0002 п.3):
        орган дважды в одной цепочке замен не появляется.
        """
        entry = self._organs.get(organ)
        if entry is None:
            self._emit("veto", organ, {"reason": "орган не объявлен в манифесте", "tool": tool}, trace_id=trace_id)
            raise SynapseVeto(f"{organ!r}: органа нет в манифесте")

        if tool not in entry["tools"]:
            self._emit("veto", organ, {"reason": "инструмент не объявлен в манифесте", "tool": tool}, trace_id=trace_id)
            raise SynapseVeto(f"{organ}.{tool}: инструмент не объявлен в манифесте")

        adapter = self._adapters.get(organ)
        if adapter is None or not self.health(organ):
            return self._substitute_or_raise(organ, tool, payload, trace_id, _seen)

        started = time.monotonic()
        try:
            with enforce(entry.get("authority") or {}, organ=organ):  # страж полномочий (SPEC-0002 п.8)
                result, cost = adapter.invoke(tool, payload or {})
        except AuthorityViolation:
            self._emit("security.violation", organ, {"reason": "превышены полномочия", "tool": tool}, trace_id=trace_id)
            raise  # нарушителя не заменяют молча — security stop (SPEC-0002)
        except Exception as exc:  # noqa: BLE001 — отказной режим SPEC-0001: событие error + замена
            self._emit("error", organ, {"reason": f"орган упал: {exc}", "tool": tool}, trace_id=trace_id)
            return self._substitute_or_raise(organ, tool, payload, trace_id, _seen)

        measured = max(float(cost.get("seconds", 0.0)) if isinstance(cost, dict) else cost.seconds, time.monotonic() - started)
        cost_dict = cost.as_dict() if hasattr(cost, "as_dict") else dict(cost)
        cost_dict["seconds"] = round(measured, 6)

        self._emit("act", organ, {"tool": tool, "payload": payload or {}}, Cost.from_dict(cost_dict), trace_id)
        return result

    def _substitute_or_raise(self, organ: str, tool: str, payload: dict[str, Any] | None, trace_id: str, _seen: frozenset[str]) -> Any:
        """Трафик уходит к замене из substitutions; замен/цикл — error и OrganUnavailable (SPEC-0002 п.3)."""
        substitute = self._find_substitute(organ, trace_id)
        if substitute is None:
            self._emit("error", organ, {"reason": "орган недоступен, замены нет", "tool": tool}, trace_id=trace_id)
            raise OrganUnavailable(f"{organ}: недоступен и замен нет")
        if substitute in _seen:
            self._emit("error", organ, {"reason": f"цикл замен: {' -> '.join((*_seen, organ, substitute))}", "tool": tool}, trace_id=trace_id)
            raise OrganUnavailable(f"{organ}: цикл в таблице замен ({substitute} уже в цепочке)")
        return self.call(substitute, tool, payload, trace_id, _seen | {organ})

    def _find_substitute(self, failed: str, trace_id: str) -> str | None:
        for reserve in self._substitutions.get(failed, []):
            if self.health(reserve):
                self._emit("organ.replace", failed, {"from": failed, "to": reserve}, trace_id=trace_id)
                return reserve
        return None
