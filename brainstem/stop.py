"""Файловый нерв внешнего аварийного стопа — SPEC-0001 v0.6.0 п.8 (W-0033, волна №24).

Сигнал — файл: есть файл — стоп, причина — первая непустая строка; пустой
файл назван честно («стоп-файл»), не придуман. Файл потребляется при
прочтении: остановка живёт в крови (halt-конверт с source=external), а не
в файле; удалить не удалось — сигнал повторится на следующем трейсе
(безопасное направление: лучше лишний стоп, чем пропущенный). Ошибка
чтения (кроме исчезнувшего файла) — исключение наружу: цикл останавливает
(fail-closed, п.8: упавший сигнал — тоже стоп).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable


def file_stop_signal(path: str | Path) -> Callable[[], str | None]:
    """Возвращает stop_signal по стоп-файлу path (SPEC-0001 п.8, W-0033).

    None — стопа нет; строка — названная причина. Файл потребляется
    при прочтении (unlink best-effort: отказ удаления сигнал не глотает).
    """
    stop_path = Path(path)

    def signal() -> str | None:
        try:
            if not stop_path.exists():
                return None
        except OSError:
            return None  # граница недоступна — судить о стопе нечем, файл мог исчезнуть
        try:
            text = stop_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None  # файл исчез между exists и read — стопа нет
        try:
            stop_path.unlink()
        except OSError:
            pass  # удалить не удалось — сигнал повторится (безопасное направление)
        for line in text.splitlines():
            if line.strip():
                return line.strip()
        return "стоп-файл"

    return signal
