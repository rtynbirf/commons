"""Журнал крови — SPEC-0003 п.4: append-only.

Переупорядочивание и удаление запрещены; всё, что записано, реконструирует сессию.

С v0.5.0 (п.7) журнал — цепочка конвертов: конверт, записанный после другого,
несёт `prev_id` — id предыдущего конверта того же файла; первый конверт файла
цепочку не несёт. Разрыв журнала (удаление, вставка, перестановка) обнаруживается
при чтении — `verify` отчитывается гэпами, гематология красит файл. Честная
граница (SPEC-0003 п.14, волна №20): подмена содержимого при сохранённых `id` и
`prev_id` цепочкой НЕ ловится — цепочка шьёт порядок, а не байты; защиты
содержимого нет до хотёлки W-0026 (`prev_sha256`), и ни один докстринг дома
не заявляет обратного. Пролитая кровь без цепочки (v0.4.0 и старше) валидна
навсегда: файл, в котором ни один конверт не несёт `prev_id`, цепочку не заявляет.

С v0.11.0 (п.14) кровь не принимает несериализуемое: `append` сериализует
конверт ДО мутации чего-либо (находка F-02 внешнего аудита 2026-11-03: раньше
несериализуемый payload оставался в памяти без строки в файле, ломал якорь
`prev_id` и рассинхронизировал память и кровь). Несериализуемый конверт —
`EnvelopeError`, и отказ записи ничего не меняет: ни строки, ни памяти, ни цепочки.

С A01 (Ф-0, волна №16) журнал помнит эффекты: повторный append того же `id`
или того же `idempotency_key` не создаёт второе событие — возвращается
записанный конверт, строка в кровь не пишется. Тот же `id` с другим
содержанием — не dedupe, а конфликт: fail-closed (EnvelopeError).

С 0.6.0 (п.9, волна №17) журнал владеет моментом записи: при append он сам
ставит конверту `stored_at` — изготовитель конверта момент записи не выдумывает.
`stored_at` (как и `prev_id`) — метаданные файла, не часть эффекта: дедуп
(A01) их конфликтом не считает.

С 0.12.0 (п.15, волна №21, W-0026) журнал шьёт и содержание: при append он
ставит конверту `prev_sha256` — канонический SHA-256 предыдущего конверта
файла. Подмена содержимого при сохранённых `id`/`prev_id` (граница п.14)
меняет канонический хэш и роняется при чтении (`verify` — content_gaps).
Хэш-цепочка транзитивна: подделка любого конверта в середине роняет ссылки
на него во всех последующих. Усечение хвоста хэшами внутри файла не ловится
по определению — против него внешний якорь: `seal` печатает файл (сколько
событий, какой хэш), `verify` с якорем красит усечение и подмену хвоста.
Конверты без `prev_sha256` (v0.4–v0.11) валидны навсегда: хэш-зона файла
начинается с первого заверённого конверта, старая кровь не заверяется —
граница честно названа, не скрыта.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from blood.envelope import Cost, EnvelopeError, canonical_sha256, now_utc, validate


class Journal:
    """Память крови. Валидирует каждый конверт до записи (SPEC-0003, отказной режим)."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._fh: Any = None
        # Якорь цепочки prev_id (SPEC-0003 п.7): id последнего известного
        # конверта. None — цепочка ещё не началась (первый конверт файла).
        self._last_id: str | None = None
        # Якорь хэш-цепочки (SPEC-0003 п.15, W-0026): канонический SHA-256
        # последнего известного конверта. None — заверять нечего (первый
        # конверт файла или старая кровь без хэшей).
        self._last_sha: str | None = None
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
        self._last_id, self._last_sha = self._last_anchor(Path(path))
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
    def _last_anchor(path: Path) -> tuple[str | None, str | None]:
        """Якорь файла для продолжения цепочек (п.7 и п.15): id и канонический
        SHA-256 последнего разобранного конверта с id.

        Битая строка и конверт без id якорем не служат — скан идёт до конца
        файла. Журналы организма — десятки килобайт: честный полный проход
        дешевле хитрых хвостов.
        """
        if not path.exists() or path.stat().st_size == 0:
            return None, None
        last_id: str | None = None
        last_sha: str | None = None
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
                    last_id = envelope["id"]
                    last_sha = canonical_sha256(envelope)
        return last_id, last_sha

    def append(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Записывает конверт, проставляя prev_id цепочки (SPEC-0003 п.7).

        Повторный append (A01) не повторяет эффект: тот же `id` или тот же
        `idempotency_key` возвращают уже записанный конверт — строка в кровь
        не пишется, цепочка и цена не дублируются. Тот же `id` с другим
        содержанием — конфликт, fail-closed (EnvelopeError).

        При записи журнал ставит `stored_at` (п.9) — момент записи знает
        журнал, не изготовитель конверта. При записи журнал ставит и
        `prev_sha256` (п.15, W-0026) — печать содержания: предыдущий конверт
        заверяется каноническим хэшем, подмена ловится при чтении.

        Возвращает записанный конверт (уже с prev_id, stored_at и prev_sha256)
        — память помнит уже записанное (SPEC-0005 п.1).
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
        # Момент записи — факт журнала (п.9): ставится сам, после валидации
        # содержания, до цепочки; изготовитель конверта его не выдумывает.
        envelope["stored_at"] = now_utc()
        if self._last_id is not None:
            envelope["prev_id"] = self._last_id
        if self._last_sha is not None:
            envelope["prev_sha256"] = self._last_sha
        # Кровь не принимает несериализуемое (SPEC-0003 п.14, волна №20, F-02):
        # сериализация ДО мутации памяти — конверт, который не упадёт в файл,
        # не должен попадать и в память; отказ записи ничего не меняет.
        try:
            line = json.dumps(envelope, ensure_ascii=False) + "\n"
        except (TypeError, ValueError) as exc:
            raise EnvelopeError(f"конверт не сериализуется в JSON, кровь не записана: {exc}") from exc
        self._events.append(envelope)
        if self._fh is not None:
            self._fh.write(line)
            self._fh.flush()
        self._last_id = envelope["id"]
        self._last_sha = canonical_sha256(envelope)
        self._by_id[envelope["id"]] = envelope
        if isinstance(envelope.get("idempotency_key"), str):
            self._key_to_id[envelope["idempotency_key"]] = envelope["id"]
        return envelope

    @staticmethod
    def _content(envelope: dict[str, Any]) -> dict[str, Any]:
        """Содержание конверта без метаданных файла — то, что сравнивается
        при повторном append: тот же id обязан нести тот же эффект.
        `prev_id` — цепочка файла; `stored_at` — момент записи (п.9), ставит
        его журнал; `prev_sha256` — печать содержания (п.15), ставит его тоже
        журнал. Все три — метаданные файла, эффект не повторяют и конфликтом
        не служат.
        """
        return {
            k: v for k, v in envelope.items()
            if k not in ("prev_id", "stored_at", "prev_sha256")
        }

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
            journal._last_sha = canonical_sha256(journal._events[-1])
        return journal

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self._events)

    def __len__(self) -> int:
        return len(self._events)


def seal(path: str | Path, *, name: str | None = None) -> dict[str, Any]:
    """Печатает файл крови внешним якорем (SPEC-0003 п.15, W-0026).

    Усечение хвоста хэш-цепочкой внутри файла не ловится по определению —
    подрезанный файл сам сшит и доволен. Против этого якорь СНАРУЖИ: сколько
    событий было и каким каноническим хэшем был запечатан последний конверт.
    Якорь — не подмена append-only: кровь не трогает, он лишь память читателя.

    Возвращает {"file", "events", "last_id", "last_sha256", "sealed_at"} —
    запись якорной книги (blood/anchors.jsonl): живой прогон опечатывает свою
    кровь, гематология сверяет файлы с книгой. Битые строки и конверты без id
    якорем не служат — печатаются только разобранные события.
    """
    events = 0
    last_id: str | None = None
    last_sha: str | None = None
    path = Path(path)
    if path.exists() and path.stat().st_size > 0:
        with path.open("rb") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                try:
                    envelope = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if not isinstance(envelope, dict) or not envelope.get("id"):
                    continue
                events += 1
                last_id = envelope["id"]
                last_sha = canonical_sha256(envelope)
    return {
        "file": name or path.name,
        "events": events,
        "last_id": last_id,
        "last_sha256": last_sha,
        "sealed_at": now_utc(),
    }


def verify(path: str | Path, anchor: dict[str, Any] | None = None) -> dict[str, Any]:
    """Целостность журнала при чтении (SPEC-0003 п.7 + п.15).

    Две цепочки, две честные границы:

    - **порядок** (`prev_id`, п.7): цепочка заявлена с первого конверта,
      несущего `prev_id`; разрыв — удаление/подмена/вставка — гэп в `gaps`.
      Кровь без цепочки (v0.4.0 и старше) валидна навсегда: `chained: false`.
    - **содержание** (`prev_sha256`, п.15, W-0026): конверт с печатью обязан
      ссылаться на канонический SHA-256 предыдущего валидного конверта файла;
      подмена содержимого — `content_gaps`. Хэш-зона начинается с первого
      заверённого конверта; кровь без печатей (`hashed: false`) содержимое не
      заверяет — старая граница п.14 остаётся названной, не скрытой.
    - **якорь** (`anchor` от `seal`): событий меньше запечатанного — усечение
      хвоста; при равенстве не совпали id/хэш последнего — подмена хвоста.
      Файл, выросший после печати, якорю верен (рост — не гэп).

    Битая строка и конверт без id якорем не служат — честный `skipped`.

    Возвращает отчёт: {"events": N, "gaps": [...], "skipped": S, "chained": bool,
    "content_gaps": [...], "hashed": bool}.
    """
    events = 0
    skipped = 0
    gaps: list[dict[str, Any]] = []
    chained = False
    chain_started = False
    prev_id_actual: str | None = None
    content_gaps: list[dict[str, Any]] = []
    hashed = False
    hash_started = False
    prev_sha_actual: str | None = None
    last_id: str | None = None
    last_sha: str | None = None

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

            declared_sha = envelope.get("prev_sha256")
            if declared_sha is not None:
                hashed = True
                hash_started = True
                if prev_sha_actual is None:
                    content_gaps.append({
                        "line": lineno,
                        "id": envelope["id"],
                        "reason": "первый конверт файла несёт prev_sha256 — нечего заверять",
                    })
                elif declared_sha != prev_sha_actual:
                    content_gaps.append({
                        "line": lineno,
                        "id": envelope["id"],
                        "reason": "подмена содержимого: prev_sha256 не совпал с каноническим хэшем предыдущего конверта",
                    })
            elif hash_started:
                content_gaps.append({
                    "line": lineno,
                    "id": envelope["id"],
                    "reason": "конверт в заверенной зоне без prev_sha256",
                })
            prev_sha_actual = canonical_sha256(envelope)
            last_id = envelope["id"]
            last_sha = prev_sha_actual

    if anchor is not None:
        anchor_events = int(anchor.get("events", 0))
        if events < anchor_events:
            content_gaps.append({
                "line": None,
                "id": anchor.get("last_id"),
                "reason": (
                    f"усечение хвоста: в файле {events} событий, "
                    f"якорь помнит {anchor_events}"
                ),
            })
        elif events == anchor_events and (
            last_id != anchor.get("last_id") or last_sha != anchor.get("last_sha256")
        ):
            content_gaps.append({
                "line": None,
                "id": anchor.get("last_id"),
                "reason": "хвост подменён: последний конверт не совпадает с запечатанным якорем (id или хэш)",
            })
        # events > anchor_events — файл вырос после печати: рост не гэп.

    return {
        "events": events,
        "gaps": gaps,
        "skipped": skipped,
        "chained": chained,
        "content_gaps": content_gaps,
        "hashed": hashed,
    }
