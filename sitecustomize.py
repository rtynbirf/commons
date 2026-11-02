# SPDX-FileCopyrightText: 2026 COMMONS contributors
# SPDX-License-Identifier: Apache-2.0
"""Загрузчик стража в детёныше (SPEC-0002 п.8, v0.7.0): конверт COMMONS_AUTHORITY в
окружении ставит процесс под полномочия органа до первого оператора; битый конверт —
детёныш не живёт (fail-closed, exit 88). Без конверта файл ничего не делает.
"""

import os
import sys

if "COMMONS_AUTHORITY" in os.environ:  # конверта нет — обычный процесс, страж не нужен
    try:
        from synapse.authority import boot_child

        boot_child(os.environ["COMMONS_AUTHORITY"])
    except BaseException:  # noqa: BLE001 — падение загрузки = детёныш без стража
        sys.exit(88)  # детёныш без стража не живёт (fail-closed, SPEC-0002 v0.7.0)
