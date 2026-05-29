from __future__ import annotations

import os
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

from control_plane.config import HERMES_CONFIG_PATH, HERMES_ENV_PATH, HERMES_HOME, HOME_DIR, load_env_file, should_autostart_gateway
from control_plane.runtime_mode import use_s6_supervision
from control_plane.s6_ops import (
    hermes_gateway_start,
    hermes_gateway_stop,
    hermes_runtime_env,
    s6_service_up,
)

_GATEWAY_SLOT = "/run/service/gateway-default"


class GatewayManager:
    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self.logs: deque[str] = deque(maxlen=1000)
        self.start_time: float | None = None
        self._lock = threading.Lock()

    def _capture_stream(self, stream) -> None:
        if stream is None:
            return
        for line in iter(stream.readline, ""):
            self.logs.append(line.rstrip())
        try:
            stream.close()
        except OSError:
            pass

    def _gateway_log_tail(self, limit: int = 100) -> list[str]:
        log_path = HERMES_HOME / "logs" / "gateway.log"
        if not log_path.is_file():
            return []
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        return lines[-limit:]

    def is_running(self) -> bool:
        if use_s6_supervision():
            up = s6_service_up(_GATEWAY_SLOT)
            if up and self.start_time is None:
                self.start_time = time.time()
            if not up:
                self.start_time = None
            return up
        return self.process is not None and self.process.poll() is None

    def start(self) -> None:
        with self._lock:
            if self.is_running():
                return
            if use_s6_supervision():
                hermes_gateway_start()
                self.start_time = time.time()
                return
            env = os.environ.copy()
            env.update(load_env_file(HERMES_ENV_PATH))
            env.update(hermes_runtime_env())
            self.process = subprocess.Popen(
                ["hermes", "gateway"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
            )
            self.start_time = time.time()
            threading.Thread(target=self._capture_stream, args=(self.process.stdout,), daemon=True).start()

    def stop(self) -> None:
        with self._lock:
            if use_s6_supervision():
                hermes_gateway_stop()
                self.process = None
                self.start_time = None
                return
            if not self.is_running():
                return
            assert self.process is not None
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)

    def restart(self) -> None:
        self.stop()
        self.start()

    def should_autostart(self) -> bool:
        return should_autostart_gateway(config_path=HERMES_CONFIG_PATH, env_path=HERMES_ENV_PATH)

    def health_ok(self) -> bool:
        """Gateway is healthy once its process has been alive for ≥3 s without exiting."""
        if not self.is_running():
            return False
        if self.start_time is None and use_s6_supervision():
            return True
        if self.start_time is None:
            return False
        return (time.time() - self.start_time) >= 3.0

    def status(self) -> dict:
        if use_s6_supervision():
            running = self.is_running()
            log_tail = self._gateway_log_tail() if running else self._gateway_log_tail()
            return {
                "running": running,
                "pid": None,
                "uptime_seconds": 0,
                "healthy": self.health_ok() if running else False,
                "autostart_eligible": self.should_autostart(),
                "log_tail": log_tail[-100:],
                "supervisor": "s6",
                "service": _GATEWAY_SLOT,
            }
        pid = self.process.pid if self.process else None
        return {
            "running": self.is_running(),
            "pid": pid,
            "uptime_seconds": int(time.time() - self.start_time) if self.start_time and self.is_running() else 0,
            "healthy": self.health_ok(),
            "autostart_eligible": self.should_autostart(),
            "log_tail": list(self.logs)[-100:],
            "supervisor": "subprocess",
        }
