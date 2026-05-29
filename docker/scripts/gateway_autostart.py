#!/usr/bin/env python3
"""Start the default-profile gateway via s6 when autostart rules are satisfied."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "/app")

from control_plane.config import should_autostart_gateway  # noqa: E402
from control_plane.runtime_mode import use_s6_supervision  # noqa: E402
from control_plane.s6_ops import hermes_gateway_start, s6_available, s6_service_up, s6_service_want_up  # noqa: E402

_GATEWAY_SLOT = "/run/service/gateway-default"


def main() -> int:
    if not use_s6_supervision():
        return 0
    if not s6_available():
        print("[all-in-one] s6 binaries missing; skipping gateway autostart", flush=True)
        return 0
    if not should_autostart_gateway():
        print("[all-in-one] gateway autostart not eligible yet", flush=True)
        return 0
    if s6_service_up(_GATEWAY_SLOT) or s6_service_want_up(_GATEWAY_SLOT):
        print("[all-in-one] gateway-default already up", flush=True)
        return 0
    try:
        hermes_gateway_start()
    except Exception as exc:  # noqa: BLE001
        print(f"[all-in-one] gateway autostart failed: {exc}", flush=True)
        return 1
    print("[all-in-one] gateway-default start requested", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
