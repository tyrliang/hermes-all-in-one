from __future__ import annotations

import os


def use_s6_supervision() -> bool:
    return os.getenv("CONTROL_PLANE_RUNTIME", "").strip().lower() == "s6"
