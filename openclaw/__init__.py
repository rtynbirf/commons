"""Эффектор openclaw (SPEC-0008, ADR-0010): руки организма в каналах человека.

Мост через CLI `openclaw gateway call <method> --json` — белый список методов,
структурные параметры, fail-closed. openclaw — руки, не второй ствол мозга:
исполняет импульсы ствола, не решает. Живой gateway — на хосте человека (PID 1).
"""

__version__ = "0.11.0"

from .adapter import ALLOWED_METHODS, EffectorResult, OpenClawAdapter, main
from .check import CheckResult, validate_policy

__all__ = [
    "ALLOWED_METHODS",
    "CheckResult",
    "EffectorResult",
    "OpenClawAdapter",
    "main",
    "validate_policy",
]
