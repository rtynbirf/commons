"""Ствол мозга (SPEC-0001): канонический цикл агента.

Единственный источник агентного цикла в организме.
PLAN → ACT → OBSERVE → REFLECT → (PLAN | HALT), бюджет G3, журнал крови G1,
правило тишины W-0032 (SPEC-0004 п.8): тишина = «нет» по-записанному.
"""

from brainstem.loop import Budget, Loop, Step
from brainstem.pid1 import PID1
from brainstem.silence import ANSWER_APPROVED, ANSWER_EXPIRED, ANSWER_VETOED, ApprovalRequest, await_approval

__all__ = [
    "ANSWER_APPROVED",
    "ANSWER_EXPIRED",
    "ANSWER_VETOED",
    "ApprovalRequest",
    "Budget",
    "Loop",
    "PID1",
    "Step",
    "await_approval",
]
