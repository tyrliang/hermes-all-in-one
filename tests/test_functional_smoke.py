"""Guard smoke resource ownership and memory isolation before backend access."""
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


@pytest.mark.parametrize("name", ["e2e-test", "e2e-test-upgrade-16"])
def test_stop_removes_only_inspected_owned_container(monkeypatch, name):
    calls = []

    def docker(args):
        calls.append(args)
        if args == ["container", "inspect", name]:
            return json.dumps([{"Id": "owned-container-id", "Config": {"Labels": {"hermes.smoke-test": "true"}}}]).encode()
        assert args == ["rm", "-f", "owned-container-id"]
        return b""

    monkeypatch.setattr(runner, "docker", docker)
    monkeypatch.setattr(sys, "argv", ["functional-smoke.py", "stop", "--name", name])
    runner.main()
    assert calls[-1] == ["rm", "-f", "owned-container-id"]


@pytest.mark.parametrize("labels", [None, {}, {"hermes.smoke-test": "false"}, {"other.owner": "true"}])
def test_stop_refuses_unowned_name_collision(monkeypatch, labels):
    def docker(args):
        assert args == ["container", "inspect", "e2e-test"]
        return json.dumps([{"Id": "unrelated-container-id", "Config": {"Labels": labels}}]).encode()

    monkeypatch.setattr(runner, "docker", docker)
    monkeypatch.setattr(sys, "argv", ["functional-smoke.py", "stop"])
    with pytest.raises(RuntimeError, match="Not a smoke-test-owned container"):
        runner.main()


@pytest.mark.parametrize("name", [
    "hermes-smoke-test", "hermes-smoke-test-managed", "production", "e2e-test-",
    "e2e-test/production", "e2e-test-UPGRADE", "e2e-test--upgrade",
])
def test_rejects_unsafe_or_obsolete_container_names(monkeypatch, name):
    def docker(args):
        pytest.fail("Invalid names must be rejected before Docker access")

    monkeypatch.setattr(runner, "docker", docker)
    monkeypatch.setattr(sys, "argv", ["functional-smoke.py", "stop", "--name", name])
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 2


@pytest.mark.parametrize("action", ["test", "start"])
@pytest.mark.parametrize("labels", [None, {}, {"hermes.smoke-test": "false"}])
def test_rejects_unowned_explicit_volume_before_starting_container(monkeypatch, action, labels):
    def docker(args):
        assert args == ["volume", "inspect", "production-data"]
        return json.dumps([{"Labels": labels}]).encode()

    monkeypatch.setattr(runner, "docker", docker)
    monkeypatch.setattr(sys, "argv", ["functional-smoke.py", action, "--volume", "production-data"])
    with pytest.raises(RuntimeError, match="Not a smoke-test-owned volume"):
        runner.main()


@pytest.mark.parametrize("volume_args,expected_volume", [
    ([], "hermes-smoke-test-managed-data"),
    (["--volume", "another-smoke-fixture"], "another-smoke-fixture"),
])
def test_start_reuses_selected_owned_volume_without_reinitializing(monkeypatch, volume_args, expected_volume):
    started = []

    def docker(args):
        if args == ["volume", "inspect", expected_volume]:
            return json.dumps([{"Labels": {"hermes.smoke-test": "true"}}]).encode()
        assert args[:2] == ["run", "-d"]
        assert args[args.index("--name") + 1] == "e2e-test"
        assert args[args.index("-v") + 1] == expected_volume + ":/opt/data"
        started.append(args)
        return b"container-id"

    monkeypatch.setattr(runner, "docker", docker)
    monkeypatch.setattr(runner, "execute", lambda *args: "ready")
    monkeypatch.setattr(sys, "argv", ["functional-smoke.py", "start", *volume_args])
    runner.main()
    assert len(started) == 1
