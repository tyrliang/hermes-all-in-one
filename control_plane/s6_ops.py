from __future__ import annotations

import os
import subprocess
from pathlib import Path

_S6_BIN = Path("/command")
_HERMES_BIN = Path("/opt/hermes/bin/hermes")


def hermes_runtime_env() -> dict[str, str]:
    from control_plane.config import HERMES_CONFIG_PATH, HERMES_HOME, HOME_DIR

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(HOME_DIR),
            "HERMES_HOME": str(HERMES_HOME),
            "HERMES_CONFIG_PATH": str(HERMES_CONFIG_PATH),
            "PYTHONUNBUFFERED": "1",
        }
    )
    return env


def s6_available() -> bool:
    return (_S6_BIN / "s6-svc").is_file() and (_S6_BIN / "s6-svstat").is_file()


def s6_svstat(service_dir: str | Path) -> str:
    result = subprocess.run(
        [str(_S6_BIN / "s6-svstat"), str(service_dir)],
        capture_output=True,
        text=True,
        env=hermes_runtime_env(),
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def s6_service_up(service_dir: str | Path) -> bool:
    stat = s6_svstat(service_dir)
    if not stat:
        return False
    return " up " in f" {stat} " or stat.endswith(" up")


def s6_service_want_up(service_dir: str | Path) -> bool:
    stat = s6_svstat(service_dir)
    if not stat:
        return False
    return "want up" in stat


def s6_svc(action: str, service_dir: str | Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    flag = {"up": "-u", "down": "-d", "once": "-o"}.get(action)
    if flag is None:
        raise ValueError(f"unknown s6 action: {action}")
    return subprocess.run(
        [str(_S6_BIN / "s6-svc"), flag, str(service_dir)],
        capture_output=True,
        text=True,
        env=hermes_runtime_env(),
        check=check,
    )


def hermes_gateway_start() -> None:
    subprocess.run(
        [str(_HERMES_BIN), "gateway", "start"],
        env=hermes_runtime_env(),
        check=True,
    )


def hermes_gateway_stop() -> None:
    subprocess.run(
        [str(_HERMES_BIN), "gateway", "stop"],
        env=hermes_runtime_env(),
        check=False,
    )
