# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Память-файлы — ТЗ-1.1 (SPEC-0005 п.7, волна №27): A11 экспорт, A13 diff, A12 forget.

Запись памяти читает человек: `export()` пишет в `commons-memory/` два файла —
`records.jsonl` (одна строка на запись: id, provenance, содержание из крови —
кровь истина, не выдумка) и `graph.json` (анатомия графа). `diff()` честно
сравнивает файлы с живой памятью; `import_files()` возвращает в память записи,
живущие в файлах (вектор — из текста конверта крови), — надгробие старше файлов.

`forget()` выметает запись из ВСЕХ контролируемых производных — индекс, граф,
файлы экспорта — и ставит надгробие в кровь (тип `forget`, SPEC-0003 п.18;
дедуп журнала делает повторное забвение тем же событием). Отчёт честен по
каждому месту:

- `DELETED` — нашли и выметали;
- `NOT_FOUND` — там её и не было;
- `FAILED` — пытались, не вышло; причина названа (полуготовность не выдаётся за успех);
- `OUT_OF_CONTROL` — кровь: append-only (SPEC-0003 п.4), исходный конверт
  остаётся в журнале навсегда — забывает память, не организм (SPEC-0005 п.6);
  тело забвением крови не управляет, и это названо, а не спрятано.

Незнакомый id — NOT_FOUND везде и ни строки в кровь. Экспорт, diff и импорт
ничего не пишут в кровь — только forget ставит надгробие.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Union

from blood.journal import Journal
from blood.provenance import knowledge_source, trust_of
from memory.replay import string_leaves

DELETED = "DELETED"
NOT_FOUND = "NOT_FOUND"
FAILED = "FAILED"
OUT_OF_CONTROL = "OUT_OF_CONTROL"

STATUSES = (DELETED, NOT_FOUND, FAILED, OUT_OF_CONTROL)

RECORDS_FILE = "records.jsonl"
GRAPH_FILE = "graph.json"


class MemoryFiles:
    """Слой между памятью и домом (SPEC-0005 п.7): экспорт / diff / импорт / forget.

    Принимает живые объекты памяти (index — VectorIndex, graph — MemoryGraph),
    журнал крови (Journal или путь к blood.jsonl — источник содержания записей)
    и каталог экспорта. Кровь не пишет нигде, кроме forget-надгробия.
    """

    def __init__(
        self,
        *,
        index: Any,
        graph: Any,
        journal: Union[Journal, str, Path] | None,
        export_dir: str | Path,
    ) -> None:
        self._index = index
        self._graph = graph
        if isinstance(journal, Journal) or journal is None:
            self._journal: Journal | None = journal
            self._blood_path: Path | None = None
        else:
            self._journal = None
            self._blood_path = Path(journal)
        self._export_dir = Path(export_dir)

    # --- чтение крови -------------------------------------------------------

    def _envelopes(self) -> list[dict[str, Any]]:
        """Все валидные конверты крови (Journal или файл) — содержание записей."""
        if self._journal is not None:
            return list(self._journal.all())
        if self._blood_path is not None and self._blood_path.exists():
            return list(Journal.from_jsonl(self._blood_path).all())
        return []

    def _envelope_by_id(self, env_id: str) -> dict[str, Any] | None:
        for envelope in self._envelopes():
            if envelope.get("id") == env_id:
                return envelope
        return None

    def _tombstoned(self) -> set[str]:
        """Id записей, на которые в крови висит надгробие (forget)."""
        return {
            envelope["payload"]["forget"]
            for envelope in self._envelopes()
            if envelope.get("type") == "forget"
            and isinstance(envelope.get("payload"), dict)
            and isinstance(envelope["payload"].get("forget"), str)
        }

    # --- A11: экспорт ---------------------------------------------------------

    def export(self) -> dict[str, Any]:
        """Записи памяти — читаемые файлы дома (A11); кровь не пишется.

        Одна строка records.jsonl на запись памяти: id, тип, источник, трейс,
        payload (из крови — истина) и provenance записи (откуда знает, доверие).
        graph.json — анатомия графа: узлы и рёбра.
        """
        self._export_dir.mkdir(parents=True, exist_ok=True)
        by_id = {e["id"]: e for e in self._envelopes() if e.get("id")}
        lines: list[str] = []
        poisoned_marked = 0
        for env_id in sorted(self._index.ids()):
            envelope = by_id.get(env_id)
            if envelope is None:
                continue  # честная граница: записи без конверта в крови содержание не выдумывается
            record = {
                "id": env_id,
                "type": envelope.get("type"),
                "source": envelope.get("source"),
                "trace_id": envelope.get("trace_id"),
                "payload": envelope.get("payload"),
                "provenance": {
                    "knowledge_source": knowledge_source(envelope),
                    "trust": trust_of(envelope),
                },
            }
            lines.append(json.dumps(record, ensure_ascii=False))
        records_file = self._export_dir / RECORDS_FILE
        records_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        graph_file = self._export_dir / GRAPH_FILE
        graph_file.write_text(
            json.dumps(self._graph.stats(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return {
            "records": len(lines),
            "records_file": str(records_file),
            "graph_file": str(graph_file),
            "poisoned_marked": poisoned_marked,
        }

    # --- A13: diff -------------------------------------------------------------

    def diff(self) -> dict[str, Any]:
        """Файлы ↔ память, без выдумок (A13): что живёт только там или только тут."""
        memory_ids = set(self._index.ids())
        file_ids = self._file_record_ids()
        return {
            "only_in_memory": sorted(memory_ids - file_ids),
            "only_in_files": sorted(file_ids - memory_ids),
            "consistent": sorted(memory_ids & file_ids),
        }

    def _records_file(self) -> Path:
        return self._export_dir / RECORDS_FILE

    def _file_record_ids(self) -> set[str]:
        records_file = self._records_file()
        if not records_file.exists():
            return set()
        ids: set[str] = set()
        for line in records_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue  # битая строка файла — не запись
            if isinstance(row, dict) and isinstance(row.get("id"), str):
                ids.add(row["id"])
        return ids

    # --- импорт ----------------------------------------------------------------

    def import_files(self) -> dict[str, Any]:
        """Ручная правка человека возвращается в память; надгробие старше файлов.

        Запись с конвертом в крови — вектор из текста конверта (кровь — истина).
        Ручная запись, которой в крови нет, — вектор из текста самой записи:
        файл — источник её знания (provenance записи объявляет это честно);
        это ЯВНАЯ операция поверх replay — G1 воспроизводит память крови,
        ручные записи возвращаются только импортом (граница SPEC-0005 п.7).
        Запись, на которую в крови висит надгробие, не возвращается никогда.
        """
        from memory import embed_text
        from memory.replay import envelope_meta, envelope_text

        dead = self._tombstoned()
        by_id = {e["id"]: e for e in self._envelopes() if e.get("id")}
        added: list[str] = []
        skipped: list[str] = []
        for env_id in sorted(self._file_record_ids()):
            if env_id in dead:
                skipped.append(env_id)
                continue
            if env_id in set(self._index.ids()):
                continue
            envelope = by_id.get(env_id)
            if envelope is not None:
                self._index.add(
                    env_id,
                    embed_text(envelope_text(envelope)),
                    envelope_meta(envelope),
                )
                self._graph.add_envelope(envelope)
            else:
                record = self._file_record(env_id)
                if record is None:
                    continue
                provenance = record.get("provenance") or {}
                meta = {
                    "type": record.get("type", ""),
                    "source": record.get("source", ""),
                    "trace_id": record.get("trace_id", ""),
                    "knowledge_source": provenance.get("knowledge_source", "human"),
                    "trust": provenance.get("trust", "unknown"),
                }
                text = " ".join(
                    str(part)
                    for part in (
                        record.get("type", ""),
                        record.get("source", ""),
                        *string_leaves(record.get("payload") or {}),
                    )
                )
                self._index.add(env_id, embed_text(text), meta)
                # граф честен по заявленному источнику записи: файл — источник знания
                self._graph.add_envelope({
                    "id": env_id,
                    "source": record.get("source") or "human",
                    "organ": "none",
                    "trace_id": record.get("trace_id") or env_id,
                    "payload": record.get("payload") or {},
                })
            added.append(env_id)
        return {"added": added, "skipped_tombstoned": skipped}

    def _file_record(self, env_id: str) -> dict[str, Any] | None:
        """Одна запись из records.jsonl по id (None — нет или битая)."""
        records_file = self._records_file()
        if not records_file.exists():
            return None
        for line in records_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("id") == env_id:
                return row
        return None

    # --- A12: forget -----------------------------------------------------------

    def forget(self, envelope_id: str, *, reason: str, by: str = "human") -> dict[str, Any]:
        """Забывает запись во всех контролируемых производных (A12) + надгробие в кровь.

        Порядок честный: сначала попытка выметания производных, потом надгробие
        (дедуп журнала делает повторное забвение тем же событием). Кровь —
        OUT_OF_CONTROL: исходный конверт остаётся навсегда, тело его не вычёркивает.
        Незнакомый id — NOT_FOUND везде, ни строки в кровь.
        """
        failed_reasons: dict[str, str] = {}

        envelope = self._envelope_by_id(envelope_id)

        index_status = self._cleanup(
            "index",
            failed_reasons,
            lambda: DELETED if self._index.forget(envelope_id) else NOT_FOUND,
        )
        graph_status = self._cleanup(
            "graph",
            failed_reasons,
            lambda: (
                DELETED
                if (envelope is not None and self._graph.forget_envelope(envelope))
                else NOT_FOUND
            ),
        )
        files_status = self._cleanup(
            "files",
            failed_reasons,
            lambda: self._forget_from_files(envelope_id),
        )

        if index_status == graph_status == files_status == NOT_FOUND and envelope is None:
            return {
                "forget": envelope_id,
                "index": NOT_FOUND,
                "graph": NOT_FOUND,
                "files": NOT_FOUND,
                "blood": NOT_FOUND,
                "tombstone": None,
                "reason": reason,
                "failed_reasons": {},
            }

        tombstone_id = None
        if self._journal is not None:
            tombstone = self._journal.append(
                _make_tombstone(envelope_id, reason=reason, by=by)
            )
            tombstone_id = tombstone["id"]

        return {
            "forget": envelope_id,
            "index": index_status,
            "graph": graph_status,
            "files": files_status,
            "blood": OUT_OF_CONTROL if envelope is not None else NOT_FOUND,
            "tombstone": tombstone_id,
            "reason": reason,
            "by": by,
            "failed_reasons": failed_reasons,
        }

    def _cleanup(self, place: str, failed_reasons: dict[str, str], action) -> str:
        """Один шаг выметания: исключение честно названо FAILED с причиной."""
        try:
            return action()
        except Exception as exc:  # noqa: BLE001 — причина сбоя названа, не спрятана
            failed_reasons[place] = repr(exc)
            return FAILED

    def _forget_from_files(self, envelope_id: str) -> str:
        """Выметает запись из файлов экспорта; файлов нет — NOT_FOUND (их не было)."""
        records_file = self._records_file()
        if not records_file.exists():
            return NOT_FOUND
        lines = records_file.read_text(encoding="utf-8").splitlines()
        kept: list[str] = []
        removed = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError:
                kept.append(stripped)
                continue
            if isinstance(row, dict) and row.get("id") == envelope_id:
                removed = True
                continue
            kept.append(stripped)
        if not removed:
            return NOT_FOUND
        records_file.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
        return DELETED


def _make_tombstone(envelope_id: str, *, reason: str, by: str) -> dict[str, Any]:
    """Надгробие в крови (SPEC-0003 п.18): тип forget, источник по воле."""
    from blood.envelope import Cost, make

    source = "pid1" if by == "human" else "brainstem"
    return make(
        "forget",
        source,
        "self",
        f"forget:{envelope_id[:8]}",
        {"forget": envelope_id, "reason": reason, "by": by},
        Cost(0, 0, 0.0),
        idempotency_key=f"forget:{envelope_id}",
    )
