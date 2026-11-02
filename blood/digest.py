"""Выжимка крови — недельный агрегат (W-0019).

SPEC-0003 п.13 (Ф-1, волна №19): дом сам выжимает смысл из своей крови —
что понял, что болело, что закрыл, чем пахнет — текстом для Человека, без
чтения логов глазами. Дневник (п.12) — по-действенный слой, выжимка —
агрегатный слой того же зерна: обе проекции только читают, кровь не
переписывают, ничего не забывают (кровь append-only — выметание запрещено,
события вне окна названы честно, не спрятаны).

Честные правила агрегата:

- окно недели считается по моменту записи (`ts`) — момент факта может быть
  старше (A02/п.10), и это не скрывается: события вне окна поименованы
  счётчиком, не выброшены;
- «болело» — счётчик провалов W-0021 (veto/halt/error/security.violation),
  алерты бюджета и повреждения файлов (гэпы цепочки, битые строки);
- «закрыл» — трейс закрыт, если последний его конверт — `halt` либо
  `reflect`; открытые трейсы названы, не приукрашены;
- «пахнет» — только измеримые сигналы: доля незаявленного времени факта,
  незаявленного доверия, неклассифицированной приватности, планы без
  причинно-связанного исполнения, максимальная задержка наблюдения;
- никакой телеметрии сверх крови: агрегат видит только то, что пролит.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from blood.envelope import Cost
from blood.refusals import REFUSAL_TYPES

WINDOW_DAYS = 7


def _parse(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return None


def _read_file(path: Path) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]]]:
    """Кровь файла: валидные конверты, честный счёт битых строк, гэпы цепочки."""
    events: list[dict[str, Any]] = []
    skipped = 0
    for raw in path.open("rb"):
        line = raw.strip()
        if not line:
            skipped += 1
            continue
        try:
            envelope = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            skipped += 1
            continue
        if isinstance(envelope, dict) and envelope.get("id"):
            events.append(envelope)
        else:
            skipped += 1
    from blood.journal import verify  # локальный импорт — цикл не нужен, но и не дешев на старте

    gaps = verify(path)["gaps"]
    return events, skipped, gaps


def week_digest(
    paths: list[Path | str],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Агрегат живой крови за окно недели — без выдумок и без забывания.

    Принимает пути к blood.jsonl. Окно — `now` минус WINDOW_DAYS по моменту
    записи. Возвращает секции «понял/болело/закрыл/пахнет» + цену + честную
    шапку (файлы, события, вне окна, битые строки, повреждения).
    """
    now = now or datetime.now(timezone.utc)
    window_start = now - timedelta(days=WINDOW_DAYS)

    in_window: list[dict[str, Any]] = []
    outside = 0
    files_scanned = 0
    broken_lines = 0
    damaged_files: list[str] = []
    refusal_files: dict[str, int] = {}

    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            continue
        files_scanned += 1
        events, skipped, gaps = _read_file(path)
        broken_lines += skipped
        if gaps:
            damaged_files.append(str(path))
        for envelope in events:
            ts = _parse(envelope.get("ts", ""))
            if ts is None or ts < window_start:
                outside += 1
                continue
            in_window.append(envelope)
        refusals_here = sum(1 for e in events if e.get("type") in REFUSAL_TYPES)
        if refusals_here:
            refusal_files[str(path)] = refusals_here

    # --- что понял -----------------------------------------------------------
    acts = [e for e in in_window if e["type"] == "act"]
    reflects = [e for e in in_window if e["type"] == "reflect"]
    verdicts = [
        (e.get("payload") or {}).get("verdict")
        for e in reflects
        if isinstance((e.get("payload") or {}).get("verdict"), str)
    ]
    organs: dict[str, int] = {}
    for e in in_window:
        organ = e.get("organ", "?")
        organs[organ] = organs.get(organ, 0) + 1
    understood = {
        "events": len(in_window),
        "traces": len({e["trace_id"] for e in in_window}),
        "acts": len(acts),
        "reflects": len(reflects),
        "verdicts": verdicts,
        "organs": organs,
    }

    # --- что болело ------------------------------------------------------------
    ached_by_type: dict[str, int] = {}
    for e in in_window:
        if e["type"] in REFUSAL_TYPES:
            ached_by_type[e["type"]] = ached_by_type.get(e["type"], 0) + 1
    alerts = [e for e in in_window if e["type"] == "alert"]
    ached = {
        "refusals": ached_by_type,
        "refusals_total": sum(ached_by_type.values()),
        "alerts": len(alerts),
        "damaged_files": damaged_files,
        "broken_lines": broken_lines,
    }

    # --- что закрыл -------------------------------------------------------------
    traces: dict[str, list[dict[str, Any]]] = {}
    for e in in_window:
        traces.setdefault(e["trace_id"], []).append(e)
    closed = 0
    open_traces: list[str] = []
    for trace_id, events in traces.items():
        last = events[-1]["type"]
        if last in ("halt", "reflect"):
            closed += 1
        else:
            open_traces.append(trace_id)
    shut = {"closed": closed, "open": open_traces}

    # --- чем пахнет ---------------------------------------------------------------
    smells: list[str] = []
    if in_window:
        no_fact_time = sum(1 for e in in_window if not isinstance(e.get("occurred_at"), str))
        if no_fact_time:
            smells.append(
                f"время факта не заявлено у {no_fact_time} из {len(in_window)} событий — "
                "момент happened читается как UNKNOWN (A02), не выдуман"
            )
        no_trust = sum(1 for e in in_window if e.get("trust") not in ("unverified", "verified", "derived", "unknown"))
        if no_trust:
            smells.append(f"доверие не заявлено у {no_trust} событий — читается unknown")
        no_privacy = sum(1 for e in in_window if e.get("privacy") not in ("public", "internal", "personal", "sensitive"))
        if no_privacy:
            smells.append(f"приватность не классифицирована у {no_privacy} событий — наружу считается sensitive")
        plans = [e for e in in_window if e["type"] == "plan"]
        executed_causes = {
            e.get("causation_id") for e in in_window
            if e["type"] == "act" and isinstance(e.get("causation_id"), str)
        }
        unfulfilled = [e for e in plans if e["id"] not in executed_causes]
        if unfulfilled:
            smells.append(f"планов без причинно-связанного исполнения: {len(unfulfilled)}")
        delays = []
        for e in in_window:
            occurred = _parse(e["occurred_at"]) if isinstance(e.get("occurred_at"), str) else None
            recorded = _parse(e["ts"])
            if occurred and recorded and recorded > occurred:
                delays.append(recorded - occurred)
        if delays:
            smells.append(f"максимальная задержка наблюдения (факт → запись): {max(delays)}")

    total = Cost()
    for e in in_window:
        total += Cost.from_dict(e["cost"])
    organ_cost: dict[str, float] = {}
    for e in acts:
        organ_cost[e.get("organ", "?")] = organ_cost.get(e.get("organ", "?"), 0.0) + float(e["cost"]["seconds"])

    return {
        "window_start": window_start.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "now": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "files_scanned": files_scanned,
        "events": len(in_window),
        "outside_window": outside,
        "understood": understood,
        "ached": ached,
        "closed": shut,
        "smells": smells,
        "price": total.as_dict(),
        "organ_seconds": organ_cost,
    }


def render_digest(paths: list[Path | str], *, now: datetime | None = None) -> str:
    """Человеческий текст недельной выжимки (markdown)."""
    d = week_digest(paths, now=now)
    lines = [
        "# Выжимка крови за неделю",
        "",
        f"Окно: {d['window_start']} … {d['now']} · файлов крови: {d['files_scanned']} · "
        f"событий в окне: {d['events']}",
        "",
    ]
    if d["outside_window"]:
        lines.append(f"Событий вне окна (не забыты — названы): {d['outside_window']}.")
    if d["ached"]["broken_lines"]:
        lines.append(f"Битых строк пропущено честно: {d['ached']['broken_lines']}.")
    if d["ached"]["damaged_files"]:
        lines.append(f"**ЖУРНАЛЫ ПОВРЕЖДЕНЫ (гэпы цепочки): {', '.join(d['ached']['damaged_files'])}**")
    lines.append("")

    u = d["understood"]
    lines.append("## Что понял")
    if d["events"] == 0:
        lines.append("За окно крови не попало — организм в окне не действовал (честно, не приукрашено).")
    else:
        lines.append(
            f"- {u['acts']} действий в {u['traces']} трейсах; прочих событий (наблюдения, вердикты, служебные): {u['events'] - u['acts']}"
        )
        for verdict, n in sorted(Counter(u["verdicts"]).items(), key=lambda x: -x[1])[:5]:
            lines.append(f"- вердикт: {verdict} ×{n}")
        organs = ", ".join(f"{k}: {v}" for k, v in sorted(u["organs"].items(), key=lambda x: -x[1])[:5])
        if organs:
            lines.append(f"- органы/цели по событиям: {organs}")
    lines.append("")

    a = d["ached"]
    lines.append("## Что болело")
    if a["refusals_total"] == 0 and a["alerts"] == 0 and not a["damaged_files"]:
        lines.append("- провалов нет — счётчик честных отказов за окно пуст (данные, не похвала)")
    else:
        for kind, n in sorted(a["refusals"].items(), key=lambda x: -x[1]):
            lines.append(f"- {kind}: {n}")
        if a["alerts"]:
            lines.append(f"- алертов бюджета: {a['alerts']}")
        for f in a["damaged_files"]:
            lines.append(f"- повреждён журнал: {f}")
    lines.append("")

    s = d["closed"]
    lines.append("## Что закрыл")
    lines.append(f"- трейсов закрыто по-записанному (halt/reflect): {s['closed']}")
    if s["open"]:
        preview = ", ".join(sorted(s["open"])[:8])
        suffix = "…" if len(s["open"]) > 8 else ""
        lines.append(
            f"- трейсов без закрытия (названы честно): {len(s['open'])} — например: {preview}{suffix}"
        )
    lines.append("")

    lines.append("## Чем пахнет")
    if d["smells"]:
        for smell in d["smells"]:
            lines.append(f"- {smell}")
    else:
        lines.append("- запахов нет: незаявленного времени/доверия/приватности нет, планы исполнены")
    lines.append("")

    price = d["price"]
    lines.append("## Цена недели")
    lines.append(f"- токены {price['tokens_in']}/{price['tokens_out']}, {price['seconds']:g} с")
    if d["organ_seconds"]:
        top = ", ".join(f"{k}: {v:g} с" for k, v in sorted(d["organ_seconds"].items(), key=lambda x: -x[1])[:5])
        lines.append(f"- самые дорогие органы по секундам: {top}")
    lines.append("")
    lines.append("Кровь не переписана и не забыта: выжимка — проекция (W-0019), события вне окна названы счётчиком.")
    lines.append("")
    return "\n".join(lines)
