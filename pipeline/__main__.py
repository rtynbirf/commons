# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Точка входа конвейера: python -m pipeline [--workflows DIR] [--compose FILE]."""

from pipeline.check import main

raise SystemExit(main())
