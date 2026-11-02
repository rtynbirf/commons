"""Журнал крови — SPEC-0003 п.4: append-only.

Переупорядочивание и удаление запрещены; всё, что записано, реконструирует сессию.

С v0.5.0 (п.7) журнал — цепочка конвертов: конверт, записанный после другого,
несёт `prev_id` — id предыдущего конверта того же файла; первый конверт файла
цепочку не несёт. Разрыв журнала (удаление, подмена, вставка) обнаруживается при
чтении — `verify` отчитывается гэпами, гематология красит файл. Пролитая кровь
без цепочки (v0.4.0 и старше) валидна навсегда: файл, в котором ни один конверт
не несёт `prev_id`, цепочку не заявляет.

С A01 (Ф-0, волна №16) журнал помнит эффекты: повторный append того же `id`
или того же `idempotency_key` не создаёт второе событие — возвращается
записанный конверт, строка в кровь не пишется. Тот же `id` с другим
содержанием — не dedupe, а конфликт: fail-closed (EnvelopeError).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from blood.envelope import Cost, EnvelopeError, validate


class Journal:
    """Память крови. Валидирует каждый конверт до записи (SPEC-0003, отказной режим)."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._fh: Any = None
        # Якорь цепочки prev_id (SPEC-0003 п.7): id последнего известного
        # конверта. None — цепочка ещё не началась (первый конверт файла).
        self._last_id: str | None = None
        # Честный счётчик битых строк при чтении (from_jsonl, п.8).
        self.skipped: int = 0
        # Память dedupe (A01, SPEC-0003): id → записанный конверт;
        # idempotency_key → id первого эффекта. Пополняется при записи,
        # attach() и from_jsonl() — повторный append не повторяет эффект.
        self._by_id: dict[str, dict[str, Any]] = {}
        self._key_to_id: dict[str, str] = {}

    def attach(self, path: str | Path) -> None:
        """Пишет кровь в файл в момент события (append-only, SPEC-0004 п.5).

        Открытие в режиме 'a': несколько сессий одного дня живут в одном
        файле и различаются trace_id; смерть процесса не теряет конвертов.
        Цепочка prev_id продолжается с последнего валидного конверта файла —
        повторная сессия не начинает журнал с чистого листа.
        """
        self._fh = open(path, "a", encoding="utf-8")
        self._last_id = self._last_valid_id(Path(path))
        self._remember_file(Path(path))

    def _remember_file(self, path: Path) -> None:
        """Восстанавливает память dedupe из файла (A01): сессия, открывшая
        журнал заново, помнит эффекты пролитой крови — повторный append
        того же id/ключа не создаст вторую строку. Битая строка якорем
        не служит; помнится всё разобранное с id — честно для retries."""
        if not path.exists() or path.stat().st_size == 0:
            return
        with path.open("rb") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                try:
                    envelope = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if not isinstance(envelope, dict):
                    continue
                env_id = envelope.get("id")
                if isinstance(env_id, str) and env_id not in self._by_id:
                    self._by_id[env_id] = envelope
                key = envelope.get("idempotency_key")
                if (
                    isinstance(key, str)
                    and key not in self._key_to_id
                    and isinstance(env_id, str)
                ):
                    self._key_to_id[key] = env_id

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    @staticmethod
    def _last_valid_id(path: Path) -> str | None:
        """id последнего валидного конверта файла (якорь цепочки, п.7).

        Битая строка и конверт без id якорем не служат — скан идёт до конца
        файла, якорем становится последний разбором пройденный конверт с id.
        Журналы организма — десятки килобайт: честный полный проход дешевле
        хитрых хвостов.
        """
        if not path.exists() or path.stat().st_size == 0:
            return None
        anchor: str | None = None
        with path.open("rb") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                try:
                    envelope = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if isinstance(envelope, dict) and envelope.get("id"):
                    anchor = envelope["id"]
        return anchor

    def append(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Записывает конверт, проставляя prev_id цепочки (SPEC-0003 п.7).

        Повторный append (A01) не повторяет эффект: тот же `id` или тот же
        `idempotency_key` возвращают уже записанный конверт — строка в кровь
        не пишется, цепочка и цена не дублируются. Тот же `id` с другим
        содержанием — конфликт, fail-closed (EnvelopeError).

        Возвращает записанный конверт (уже с prev_id) — память помнит
        уже записанное (SPEC-0005 п.1).
        """
        envelope = dict(envelope)
        env_id = envelope.get("id")
        if isinstance(env_id, str) and env_id in self._by_id:
            stored = self._by_id[env_id]
            if self._content(envelope) != self._content(stored):
                raise EnvelopeError(
                    f"повторный id {env_id} с другим содержанием — конфликт, не dedupe"
                )
            return dict(stored)
        key = envelope.get("idempotency_key")
        if isinstance(key, str) and key in self._key_to_id:
            return dict(self._by_id[self._key_to_id[key]])
        validate(envelope)
        if self._last_id is not None:
            envelope["prev_id"] = self._last_id
        self._events.append(envelope)
        if self._fh is not None:
            self._fh.write(json.dumps(envelope, ensure_ascii=False) + "\n")
            self._fh.flush()
        self._last_id = envelope["id"]
        self._by_id[envelope["id"]] = envelope
        if isinstance(envelope.get("idempotency_key"), str):
            self._key_to_id[envelope["idempotency_key"]] = envelope["id"]
        return envelope

    @staticmethod
    def _content(envelope: dict[str, Any]) -> dict[str, Any]:
        """Содержание конверта без цепочки prev_id — то, что сравнивается
        при повторном append: тот же id обязан нести тот же эффект."""
        return {k: v for k, v in envelope.items() if k != "prev_id"}

    def all(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._events)

    def by_trace(self, trace_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(e for e in self._events if e["trace_id"] == trace_id)

    def by_type(self, event_type: str) -> tuple[dict[str, Any], ...]:
        return tuple(e for e in self._events if e["type"] == event_type)

    def types(self) -> list[str]:
        return [e["type"] for e in self._events]

    def totals(self, trace_id: str | None = None) -> Cost:
        selected = self.by_trace(trace_id) if trace_id else self.all()
        total = Cost()
        for event in selected:
            total += Cost.from_dict(event["cost"])
        return total

    def to_jsonl(self, path: str | Path) -> None:
        """Снимок журнала в JSONL (порядок сохранён)."""
        Path(path).write_text(
            "\n".join(json.dumps(e, ensure_ascii=False) for e in self._events) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "Journal":
        """Читает файл крови в память (SPEC-0003 п.8: resume).

        Валидные конверты — в журнал, битые строки (не JSON / не dict /
        не валидный конверт) — честный счётчик `skipped`: кровь append-only,
        мусор в ней возможен, истина — в неповреждённых конвертах.
        Цепочка продолжается с последнего загруженного конверта.
        """
        journal = cls()
        with Path(path).open("rb") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    journal.skipped += 1
                    continue
                try:
                    envelope = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    journal.skipped += 1
                    continue
                if not isinstance(envelope, dict):
                    journal.skipped += 1
                    continue
                try:
                    validate(envelope)
                except EnvelopeError:
                    journal.skipped += 1
                    continue
                journal._events.append(envelope)
                env_id = envelope["id"]
                if env_id not in journal._by_id:
                    journal._by_id[env_id] = envelope
                key = envelope.get("idempotency_key")
                if isinstance(key, str) and key not in journal._key_to_id:
                    journal._key_to_id[key] = env_id
        if journal._events:
            journal._last_id = journal._events[-1]["id"]
        return journal

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self._events)

    def __len__(self) -> int:
        return len(self._events)


def verify(path: str | Path) -> dict[str, Any]:
    """Целостность журнала при чтении (SPEC-0003 п.7): гэпы цепочки prev_id.

    Цепочка заявлена с первого конверта, несущего `prev_id`; каждый конверт
    после него обязан нести `prev_id`, равный id предыдущего валидного
    конверта файла, иначе — разрыв. Первый конверт файла с `prev_id` — гэп
    (цепочка не могла начаться). Битая строка и конверт без id якорем цепочки
    не служат — честный `skipped`. Пролитая кровь без цепочки (v0.4.0 и
    старше) валидна навсегда: `chained: false`, гэпов нет.

    Возвращает отчёт: {"events": N, "gaps": [...], "skipped": S, "chained": bool}.
    """
    events = 0
    skipped = 0
    gaps: list[dict[str, Any]] = []
    chained = False
    chain_started = False
    prev_id_actual: str | None = None

    with Path(path).open("rb") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                skipped += 1
                continue
            try:
                envelope = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                skipped += 1
                continue
            if not isinstance(envelope, dict) or not envelope.get("id"):
                skipped += 1
                continue

            events += 1
            declared = envelope.get("prev_id")
            if declared is not None:
                chained = True
                chain_started = True
                if prev_id_actual is None:
                    gaps.append({
                        "line": lineno,
                        "id": envelope["id"],
                        "reason": "первый конверт файла несёт prev_id — цепочка не могла начаться",
                    })
                elif declared != prev_id_actual:
                    gaps.append({
                        "line": lineno,
                        "id": envelope["id"],
                        "reason": f"разрыв: prev_id {declared} != фактическому предыдущему id {prev_id_actual}",
                    })
            elif chain_started:
                gaps.append({
                    "line": lineno,
                    "id": envelope["id"],
                    "reason": "конверт в цепочке без prev_id",
                })
            prev_id_actual = envelope["id"]

    return {"events": events, "gaps": gaps, "skipped": skipped, "chained": chained}
