# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Иммунная система COMMONS (SPEC-0006): лицензионный барьер на входе органа в тело.

Матрица правил — данные (immune/license-matrix.yaml, G2); barrier.py — только
механизм применения. Гейт: python -m immune [paths...] -> код 0/1 (fail-closed, G1).
"""

from immune.barrier import Decision, check_entries, load_matrix, run_check, verdict

__version__ = "0.7.0"
__all__ = ["Decision", "load_matrix", "verdict", "check_entries", "run_check"]
