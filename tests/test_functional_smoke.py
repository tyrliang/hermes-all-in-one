"""Production memory must be rejected before any network/backend initialization."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

spec = importlib.util.spec_from_file_location("functional_smoke", Path(__file__).resolve().parents[1] / "scripts/functional-smoke.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.mark.parametrize("config", [
    {"bank_id": "personal"},
    {"bank_id": "hermes-smoke-test-valid", "bank_id_template": "personal"},
    {"bank_id": "hermes-smoke-test-valid", "additional_banks": ["personal"]},
    {"bank_id": "hermes-smoke-test-valid", "recall_additional_banks": ["personal"]},
    {"bank_id": "hermes-smoke-test-valid", "mirror_to_own_bank": True},
])
def test_rejects_unsafe_bank_before_backend_initialization(tmp_path, config):
    # Substitute only the filesystem location; execute the actual in-container guard.
    home = tmp_path / ".hermes"
    (home / "hindsight").mkdir(parents=True)
    (home / "hindsight/config.json").write_text(json.dumps(config))
    code = runner.MEMORY.replace("/opt/data/.hermes", str(home))
    result = subprocess.run([sys.executable, "-c", code], text=True, capture_output=True, timeout=10)
    assert result.returncode != 0
    assert "Refusing" in result.stderr
    assert "FileNotFoundError" not in result.stderr
    assert "ModuleNotFoundError" not in result.stderr
