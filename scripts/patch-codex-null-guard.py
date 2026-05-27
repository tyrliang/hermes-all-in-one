#!/usr/bin/env python3
"""
Post-sync patch: guard against response.output=null from Codex backend.

The OpenAI Codex endpoint (chatgpt.com/backend-api/codex) can return
"output": null in its response.completed SSE event. The SDK iterates
response.output without a null check, causing TypeError.

This script patches the vendored codex transport to only send the tools
kwarg when tools are present, avoiding a secondary crash path where
providers reject tools=null.

Idempotent -- safe to run multiple times.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
CODEX_TRANSPORT = ROOT / "vendor/hermes-agent/agent/transports/codex.py"

OLD = '''\
            "tools": _responses_tools(tools),
            "tool_choice": "auto",
            "parallel_tool_calls": True,
            "store": False,
        }'''

NEW = '''\
            "store": False,
        }
        _rtools = _responses_tools(tools)
        if _rtools:
            kwargs["tools"] = _rtools
            kwargs["tool_choice"] = "auto"
            kwargs["parallel_tool_calls"] = True'''


def main() -> None:
    if not CODEX_TRANSPORT.exists():
        sys.exit(f"[patch] Not found: {CODEX_TRANSPORT}")

    src = CODEX_TRANSPORT.read_text(encoding="utf-8")

    if OLD not in src:
        if "_rtools = _responses_tools(tools)" in src:
            print("[patch] codex transport already patched.")
        else:
            print("[patch] codex transport source differs from expected -- skipping.")
        return

    patched = src.replace(OLD, NEW, 1)
    CODEX_TRANSPORT.write_text(patched, encoding="utf-8")
    print(f"[patch] Updated {CODEX_TRANSPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
