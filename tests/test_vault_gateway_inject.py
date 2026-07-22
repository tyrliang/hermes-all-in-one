"""Unit tests for Hermes Vault-aware channel/provider detection + inject helper."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
import yaml

from control_plane.config import (
    has_valid_channel_credentials,
    has_valid_provider_setup,
    has_vault_channel_bindings,
    hermes_vault_env_bindings,
    should_autostart_gateway,
)

ROOT = Path(__file__).resolve().parents[1]
INJECT_PATH = ROOT / "docker" / "scripts" / "hermes-vault-env-inject.py"


def _load_inject_module():
    spec = importlib.util.spec_from_file_location("hermes_vault_env_inject", INJECT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_hermes_vault_env_bindings_parses_map():
    cfg = {
        "secrets": {
            "hermes_vault": {
                "env": {
                    "TELEGRAM_BOT_TOKEN": "hv://telegram",
                    "OPENROUTER_API_KEY": "hv://openrouter",
                    "EMPTY": "  ",
                }
            }
        }
    }
    bindings = hermes_vault_env_bindings(cfg)
    assert bindings["TELEGRAM_BOT_TOKEN"] == "hv://telegram"
    assert bindings["OPENROUTER_API_KEY"] == "hv://openrouter"
    assert "EMPTY" not in bindings


def test_has_valid_channel_credentials_accepts_vault_only_telegram():
    assert has_valid_channel_credentials({}) is False
    cfg = {"secrets": {"hermes_vault": {"env": {"TELEGRAM_BOT_TOKEN": "hv://telegram"}}}}
    assert has_vault_channel_bindings(cfg) is True
    assert has_valid_channel_credentials({}, cfg) is True
    # plaintext still works without config
    assert has_valid_channel_credentials({"TELEGRAM_BOT_TOKEN": "123:abc"}) is True


def test_has_valid_provider_setup_accepts_vault_api_key(tmp_path: Path):
    cfg = {
        "model": {"provider": "openrouter", "default": "anthropic/claude-sonnet-4.6"},
        "secrets": {"hermes_vault": {"env": {"OPENROUTER_API_KEY": "hv://openrouter"}}},
    }
    assert has_valid_provider_setup(cfg, {}) is True
    assert has_valid_provider_setup(
        {"model": {"provider": "openrouter", "default": "x"}},
        {},
    ) is False


def test_should_autostart_with_vault_only_channel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg_path = tmp_path / "config.yaml"
    env_path = tmp_path / ".env"
    cfg = {
        "model": {"provider": "openrouter", "default": "anthropic/claude-sonnet-4.6"},
        "secrets": {
            "hermes_vault": {
                "env": {
                    "TELEGRAM_BOT_TOKEN": "hv://telegram",
                    "OPENROUTER_API_KEY": "hv://openrouter",
                }
            }
        },
    }
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    env_path.write_text("", encoding="utf-8")
    monkeypatch.setenv("HERMES_GATEWAY_AUTOSTART", "auto")
    assert (
        should_autostart_gateway(
            config_path=cfg_path,
            env_path=env_path,
            autostart_mode="auto",
        )
        is True
    )


def test_inject_script_check_and_bindings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mod = _load_inject_module()
    home = tmp_path / ".hermes"
    home.mkdir()
    cfg = {
        "secrets": {
            "hermes_vault": {
                "binary": "/usr/local/bin/hermes-vault",
                "env": {"TELEGRAM_BOT_TOKEN": "hv://telegram", "TAVILY_API_KEY": "hv://tavily"}
            }
        }
    }
    (home / "config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv("HERMES_VAULT_BINARY", raising=False)
    monkeypatch.setattr(mod, "HERMES_HOME", home)
    monkeypatch.setattr(mod, "CONFIG", home / "config.yaml")
    monkeypatch.setattr(mod, "VAULT_HOME", home / "hermes-vault-data")
    monkeypatch.setattr(mod, "STAMP", home / "hermes-vault-data" / "last-env-inject.json")

    loaded = mod._load_config()
    bindings = mod._bindings(loaded)
    assert "TELEGRAM_BOT_TOKEN=hv://telegram" in bindings
    assert "TAVILY_API_KEY=hv://tavily" in bindings
    assert mod._resolve_binary(loaded) == "/usr/local/bin/hermes-vault"

    # Without passphrase, fetch returns empty + error marker — still exit 0.
    monkeypatch.delenv("HERMES_VAULT_PASSPHRASE", raising=False)
    payload = mod._fetch(bindings, binary=mod._resolve_binary(loaded))
    assert payload["secrets"] == {}
    assert "_" in payload["errors"]


def test_resolve_binary_prefers_env_then_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mod = _load_inject_module()
    home = tmp_path / ".hermes"
    home.mkdir()
    cfg = {"secrets": {"hermes_vault": {"binary": "/from/config/hermes-vault", "env": {}}}}
    (home / "config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    monkeypatch.setattr(mod, "CONFIG", home / "config.yaml")
    monkeypatch.delenv("HERMES_VAULT_BINARY", raising=False)
    assert mod._resolve_binary() == "/from/config/hermes-vault"
    monkeypatch.setenv("HERMES_VAULT_BINARY", "/from/env/hermes-vault")
    assert mod._resolve_binary() == "/from/env/hermes-vault"
