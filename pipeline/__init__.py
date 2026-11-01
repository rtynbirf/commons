# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Конвейер COMMONS (SPEC-0007): n8n как внешний узел — артефакты-данные и валидатор.

n8n не встраивается (ADR-0009): организм даёт детерминированные точки входа,
конвейер — только данные (compose и воркфлоу JSON), проверяемые валидатором
как код. Гейт: python -m pipeline [--workflows DIR] [--compose FILE] -> код 0/1
(fail-closed, G1).
"""

from pipeline.check import CheckResult, main, run_check, validate_compose, validate_workflow

__version__ = "0.9.0"
__all__ = ["CheckResult", "validate_workflow", "validate_compose", "run_check", "main"]
