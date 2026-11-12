#!/usr/bin/env python3
"""Read-only export of a minimal Hermes fixture; run INSIDE the source container.

No credentials, conversations, identity files, bot configuration, or production
memory-bank identifiers are exported. The caller supplies a dedicated LLM key.
"""
import base64
import hashlib
import json
import os
from pathlib import Path

import yaml

root = Path(os.environ.get("HERMES_HOME", "/opt/data/.hermes"))
source = yaml.safe_load((root / "config.yaml").read_text())
provider = next(p for p in source["custom_providers"] if p["name"] == "bifrost")
plugin = root / "plugins/hindsight"
files = {}
for path in sorted(plugin.iterdir()):
    if path.is_file() and (path.suffix == ".py" or path.name in {"plugin.yaml", "pyproject.toml"}):
        files[path.name] = base64.b64encode(path.read_bytes()).decode()
assert {"__init__.py", "plugin.yaml", "pyproject.toml"} <= files.keys()
config = {
    "model": {"provider": "custom:bifrost", "default": source["model"]["default"], "base_url": provider["base_url"]},
    "custom_providers": [{"name": "bifrost", "provider_key": "bifrost", "key_env": "BIFROST_API_KEY", "base_url": provider["base_url"], "api_mode": "chat_completions", "extra_headers": {"x-bf-passthrough-extra-params": "true"}}],
    "terminal": {"backend": "local", "cwd": "/opt/data/workspace", "home_mode": "real", "timeout": 30},
    "toolsets": ["hermes-cli"],
    "memory": {"provider": "hindsight", "memory_enabled": True, "user_profile_enabled": False},
    "plugins": {"enabled": ["hindsight"]},
    "cron": {"enabled": False},
    "agent": {"max_turns": 8},
}
print(json.dumps({"config": config, "plugin_files": files, "plugin_sha256": hashlib.sha256((plugin / "__init__.py").read_bytes()).hexdigest(), "memory_url": source["hindsight"]["api_url"]}))
