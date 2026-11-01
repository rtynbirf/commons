"""Ствол мозга (SPEC-0001): канонический цикл агента.

Единственный источник агентного цикла в организме.
PLAN → ACT → OBSERVE → REFLECT → (PLAN | HALT), бюджет G3, журнал крови G1.
"""

from brainstem.loop import Budget, Loop, Step

__all__ = ["Budget", "Loop", "Step"]
