#!/usr/bin/env python3
"""Materialize Hermes Vault secrets for the gateway parent process.

Hermes Secret Source plugins register during ``discover_plugins()``, which runs
*after* the first ``load_hermes_dotenv()`` at import time. Cron sessions call
``reset_secret_source_cache()`` and re-apply sources, so outbound Telegram from
cron works even when the gateway parent never received ``TELEGRAM_BOT_TOKEN``.

This helper fetches ``secrets.hermes_vault.env`` bindings via
``hermes-vault secret-source fetch`` and either:

* prints ``export KEY='…'`` lines (for ``eval`` from a shell wrapper), or
* prints a JSON object ``{"secrets": {...}, "errors": {...}}`` (``--format json``).

No-op (exit 0, empty secrets) when vault is not configured — missing binary,
missing passphrase, or empty env map — so images without vault stay healthy.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", "/opt/data/.hermes"))
VAULT_HOME = Path(
    os.environ.get("HERMES_VAULT_HOME", str(HERMES_HOME / "hermes-vault-data"))
)
STAMP = VAULT_HOME / "last-env-inject.json"
CONFIG = HERMES_HOME / "config.yaml"
DEFAULT_BINARY = os.environ.get("HERMES_VAULT_BINARY", "hermes-vault")


def _bindings() -> list[str]:
    try:
        import yaml  # type: ignore
    except Exception as exc:  # pragma: no cover
        print(f"[vault-inject] pyyaml missing: {exc}", file=sys.stderr)
        return []
    if not CONFIG.is_file():
        return []
    try:
        data = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        print(f"[vault-inject] config read failed: {exc}", file=sys.stderr)
        return []
    env_map = ((data.get("secrets") or {}).get("hermes_vault") or {}).get("env") or {}
    out: list[str] = []
    if isinstance(env_map, dict):
        for key, value in env_map.items():
            if isinstance(key, str) and isinstance(value, str) and value.strip():
                out.append(f"{key}={value.strip()}")
    return out


def _fetch(bindings: list[str]) -> dict:
    if not bindings:
        return {"secrets": {}, "errors": {}}
    if not os.environ.get("HERMES_VAULT_PASSPHRASE"):
        return {"secrets": {}, "errors": {"_": "HERMES_VAULT_PASSPHRASE unset"}}

    cmd = [
        DEFAULT_BINARY,
        "--no-banner",
        "secret-source",
        "fetch",
        "--agent",
        "hermes",
        "--ttl",
        "3600",
        "--format",
        "json",
        "--",
        *bindings,
    ]
    env = os.environ.copy()
    env.setdefault("HERMES_VAULT_HOME", str(VAULT_HOME))
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, env=env, timeout=45, check=False
        )
    except FileNotFoundError:
        return {"secrets": {}, "errors": {"_": f"{DEFAULT_BINARY} not found"}}
    except subprocess.TimeoutExpired:
        return {"secrets": {}, "errors": {"_": "fetch timed out"}}
    except Exception as exc:  # noqa: BLE001
        return {"secrets": {}, "errors": {"_": f"fetch failed: {exc}"}}

    if proc.returncode != 0 and not (proc.stdout or "").strip():
        return {
            "secrets": {},
            "errors": {
                "_": f"fetch rc={proc.returncode} stderr={(proc.stderr or '')[:200]}"
            },
        }
    try:
        payload = json.loads(proc.stdout or "{}")
    except Exception as exc:  # noqa: BLE001
        return {"secrets": {}, "errors": {"_": f"bad json: {exc}"}}
    if not isinstance(payload, dict):
        return {"secrets": {}, "errors": {"_": "unexpected payload type"}}
    return payload


def _write_stamp(secrets: dict, errors: dict, binding_count: int) -> None:
    lengths = {
        k: len(v)
        for k, v in secrets.items()
        if isinstance(k, str) and isinstance(v, str)
    }
    try:
        VAULT_HOME.mkdir(parents=True, exist_ok=True)
        STAMP.write_text(
            json.dumps(
                {
                    "n": len(lengths),
                    "bindings": binding_count,
                    "keys": sorted(lengths.keys()),
                    "lengths": lengths,
                    "errors": list(errors.keys()) if errors else [],
                    "at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[vault-inject] stamp write failed: {exc}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--format",
        choices=("env", "json"),
        default="env",
        help="env: shell exports for eval; json: machine-readable secrets object",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="Print binding count + last stamp; do not fetch",
    )
    args = ap.parse_args()

    bindings = _bindings()
    if args.check:
        stamp: dict = {}
        if STAMP.exists():
            try:
                stamp = json.loads(STAMP.read_text(encoding="utf-8"))
            except Exception:
                stamp = {"error": "unreadable stamp"}
        print(json.dumps({"bindings": len(bindings), "stamp": stamp}, indent=2))
        return 0

    payload = _fetch(bindings)
    secrets = payload.get("secrets") or {}
    errors = payload.get("errors") or {}
    if not isinstance(secrets, dict):
        secrets = {}
    if not isinstance(errors, dict):
        errors = {}

    clean: dict[str, str] = {}
    for key, value in secrets.items():
        if isinstance(key, str) and isinstance(value, str) and value:
            clean[key] = value

    _write_stamp(clean, errors, len(bindings))

    if args.format == "json":
        print(json.dumps({"secrets": clean, "errors": errors, "bindings": len(bindings)}))
        return 0

    for key, value in clean.items():
        print(f"export {key}={shlex.quote(value)}")
    print(
        f"echo '[vault-inject] applied {len(clean)}/{len(bindings)} secret(s)' >&2"
    )
    if errors:
        print(f"echo '[vault-inject] errors={list(errors.keys())}' >&2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
