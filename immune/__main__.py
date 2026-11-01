# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Точка входа иммунного барьера: python -m immune [--matrix PATH] [paths...]."""

from immune.barrier import main

raise SystemExit(main())
