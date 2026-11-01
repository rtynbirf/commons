"""PID 1 — живой организм (SPEC-0004): ритм BOOT → HEARTBEAT → SHUTDOWN.

Доктрина ЧЕЛОВЕК=PID=1 (ADR-0006): init'ом организма остаётся человек.
Организм дышит: каждые `interval` секунд опрашивает здоровье всех органов
манифеста и пишет каждое событие в кровь на диск в момент события (G1).
Любая управляемая остановка записывается: сигнал человека, бюджет (G3),
второй экземпляр. Инварианты: G1 трассируемость, G4 смерть с записью,
G5 человек-инициатор, G6 одиночность.

Коды выхода: 0 — чистая смерть; 1 — не стартовал; 2 — бюджет исчерпан.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from blood.envelope import Cost, make, new_trace_id
from blood.journal import Journal
from blood.pidlock import LockHeld, PIDLock
from synapse.gateway import Gateway, GatewayConfigError
from brainstem.loop import Budget

SLEEP_CHUNK = 0.2  # сон кусочками: сигнал человека не ждёт interval


class PID1:
    """Живой организм: демон-сердцебиение под человеком (SPEC-0004)."""

    def __init__(
        self,
        gateway: Gateway,
        journal: Journal,
        interval: float = 30.0,
        budget: Any = None,
        lock: PIDLock | None = None,
        run_dir: Path | None = None,
    ) -> None:
        self.gateway = gateway
        self.journal = journal
        self.interval = interval
        self.budget = budget
        self.lock = lock
        self.run_dir = run_dir
        self._stop_reason: str | None = None
        self._health: dict[str, int] = {}  # орган -> биений healthy

    # --- управление (человек / сигнал / тест) ---

    def request_shutdown(self, reason: str) -> None:
        """Просьба об остановке (SPEC-0004 G4): причина станет `shutdown`."""
        if self._stop_reason is None:
            self._stop_reason = reason

    # --- жизнь ---

    def run(self, max_beats: int | None = None) -> int:
        """Живёт до сигнала/бюджета/лимита биений. Возвращает код выхода."""
        trace_id = new_trace_id()

        if self.run_dir is not None:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            self.journal.attach(self.run_dir / "blood.jsonl")

        try:
            if self.lock is not None:
                try:
                    self.lock.acquire()
                except LockHeld as held:
                    # G6: второй организм не входит в живое тело — и умирает по-записанному
                    self._emit(trace_id, "veto", "self", {"reason": f"второй организм жив: {held}"})
                    self._emit(trace_id, "shutdown", "self", {"reason": "second_instance", "beats": 0})
                    return 1

            organs = self.gateway.organ_names
            self._emit(trace_id, "boot", "self", {
                "pid": os.getpid(),
                "interval": self.interval,
                "organs": organs,
            })

            exit_code = 0
            beats = 0
            reason: str | None = None
            while self._stop_reason is None:
                if self.budget is not None:
                    exhausted = self.budget.exhausted_by(self.journal.totals(trace_id))
                    if exhausted is not None:
                        reason, exit_code = f"budget:{exhausted}", 2
                        break
                if max_beats is not None and beats >= max_beats:
                    reason = "max_beats"
                    break
                self._beat(trace_id)
                beats += 1
                self._sleep()

            if reason is None:
                reason = self._stop_reason or "unknown"
            self._shutdown(trace_id, reason, beats)
            return exit_code
        finally:
            self.journal.close()
            if self.lock is not None:
                self.lock.release()

    # --- фазы ---

    def _beat(self, trace_id: str) -> None:
        """Одно биение: healthcheck всех органов манифеста (SPEC-0004 п.3)."""
        for organ in self.gateway.organ_names:
            started = time.monotonic()
            healthy = self.gateway.health(organ)
            seconds = round(time.monotonic() - started, 6)
            self._health[organ] = self._health.get(organ, 0) + (1 if healthy else 0)
            self._emit(
                trace_id, "organ.health", organ,
                {"healthy": healthy, "tool": "health"},
                Cost(seconds=seconds),
            )

    def _shutdown(self, trace_id: str, reason: str, beats: int) -> None:
        """Смерть по-записанному (G4): shutdown + отчёт; органы-процессы закрываются."""
        self._close_children()
        totals = self.journal.totals(trace_id)
        self._emit(trace_id, "shutdown", "self", {
            "reason": reason,
            "beats": beats,
            "totals": totals.as_dict(),
        })
        if self.run_dir is not None:
            self._write_report(trace_id, reason, beats)

    def _close_children(self) -> None:
        """SPEC-0002 п.7: органы-процессы умирают по вызову, не сиротами."""
        for adapter in self.gateway.adapters:
            shutdown = getattr(adapter, "shutdown", None)
            if callable(shutdown):
                try:
                    shutdown()
                except Exception:  # noqa: BLE001 — умирающий орган не держит тело
                    pass

    # --- кровь и сон ---

    def _emit(
        self,
        trace_id: str,
        event_type: str,
        organ: str,
        payload: dict[str, Any],
        cost: Cost | None = None,
    ) -> None:
        self.journal.append(make(event_type, "pid1", organ, trace_id, payload, cost))

    def _sleep(self) -> None:
        """Интервал сердцебиения кусочками — сигнал не должен ждать interval."""
        deadline = time.monotonic() + self.interval
        while time.monotonic() < deadline and self._stop_reason is None:
            time.sleep(min(SLEEP_CHUNK, deadline - time.monotonic()))

    # --- отчёт сессии (G1) ---

    def _write_report(self, trace_id: str, reason: str, beats: int) -> None:
        events = self.journal.by_trace(trace_id)
        types = [e["type"] for e in events]
        totals = self.journal.totals(trace_id)
        organs = self.gateway.organ_names
        lines = [
            "# PID 1: отчёт сессии",
            "",
            f"- trace_id: `{trace_id}`",
            f"- дата остановки: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            f"- причина: `{reason}`; биений: {beats}",
            f"- конвертов в трейсе: {len(events)}; последовательность: `{' -> '.join(types)}`",
            f"- цена сессии: tokens_in={totals.tokens_in}, tokens_out={totals.tokens_out},"
            f" seconds={round(totals.seconds, 6)}",
            "",
            "## Здоровье органов",
            "",
        ]
        for organ in organs:
            healthy = self._health.get(organ, 0)
            share = f"{healthy}/{beats}" if beats else "0/0"
            lines.append(f"- `{organ}`: здоров в {share} биений")
        lines += [
            "",
            "Кровь сессии — `blood.jsonl` рядом; каждый конверт валиден по схеме (SPEC-0003).",
            "",
        ]
        (self.run_dir / f"report-{trace_id}.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Запуск живого организма человеком (G5: только человек, только рукой)."""
    parser = argparse.ArgumentParser(
        prog="commons-pid1",
        description="COMMONS PID 1 — живой организм: BOOT → HEARTBEAT → SHUTDOWN (SPEC-0004)",
    )
    parser.add_argument("--interval", type=float, default=30.0, help="период сердцебиения, сек")
    parser.add_argument("--budget-seconds", type=float, default=3600.0, help="бюджет сессии, сек (G3)")
    parser.add_argument("--max-beats", type=int, default=None, help="остановиться после N биений")
    parser.add_argument("--manifest", default="synapse/mcp-manifest.yaml", help="путь к манифесту")
    parser.add_argument("--runs-dir", default="runs", help="каталог артефактов жизни")
    args = parser.parse_args(argv)

    journal = Journal()
    try:
        gateway = Gateway(args.manifest, journal)
    except GatewayConfigError as exc:
        print(f"pid1: манифест отклонён — организм не стартует: {exc}", file=sys.stderr)
        return 1

    run_dir = Path(args.runs_dir) / f"{datetime.now(timezone.utc).date()}-pid1"
    organism = PID1(
        gateway,
        journal,
        interval=args.interval,
        budget=Budget(seconds=args.budget_seconds),
        lock=PIDLock(Path(args.runs_dir) / ".pid1.lock"),
        run_dir=run_dir,
    )

    def _on_signal(signum: int, _frame: Any) -> None:
        name = signal.Signals(signum).name
        organism.request_shutdown(f"signal:{name}")

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    return organism.run(max_beats=args.max_beats)

if __name__ == "__main__":
    raise SystemExit(main())
