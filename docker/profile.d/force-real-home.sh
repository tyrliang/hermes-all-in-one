#!/bin/sh
# Force real home directory when TERMINAL_HOME_MODE=real
# This ensures interactive shells (including WebUI PTY) use /opt/data
# instead of the legacy fake home at /opt/data/.hermes/home.

if [ "${TERMINAL_HOME_MODE:-}" = "real" ]; then
    export HOME=/opt/data
fi