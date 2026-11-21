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

volume_spec = importlib.util.spec_from_file_location(
    "functional_volume_smoke", Path(__file__).resolve().parents[1] / "scripts/functional-volume.py"
)
volume_helper = importlib.util.module_from_spec(volume_spec)
volume_spec.loader.exec_module(volume_helper)


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
def test_rejects_unowned_explicit_volume_before_starting_container(monkeypatch, tmp_path, action, labels):
    volumes = {"production-data": {"Labels": labels}}
    containers = {}
    retained = tmp_path / "production-data"
    retained.write_bytes(b"production data")

    def docker(args, data=None):
        if args[:2] == ["volume", "inspect"]:
            return json.dumps([volumes[args[-1]]]).encode()
        if args[:2] == ["container", "ls"]:
            return "\n".join(containers).encode()
        if args[0] == "run":
            containers[args[args.index("--name") + 1]] = args[args.index("-v") + 1]
            return b"unexpected-container"
        pytest.fail(f"Unexpected Docker operation: {args!r}")

    def unexpected_runner_docker(*args, **kwargs):
        pytest.fail("Fixture volume access must go through the host transaction")

    monkeypatch.setattr(volume_helper, "LOCK_ROOT", tmp_path / "locks")
    monkeypatch.setattr(volume_helper, "docker", docker)
    monkeypatch.setattr(runner, "fixture_operation", volume_helper.run)
    monkeypatch.setattr(runner, "docker", unexpected_runner_docker)
    monkeypatch.setattr(sys, "argv", ["functional-smoke.py", action, "--volume", "production-data"])
    with pytest.raises(RuntimeError, match="Not a smoke-test-owned volume"):
        runner.main()
    assert containers == {}
    assert volumes == {"production-data": {"Labels": labels}}
    assert retained.read_bytes() == b"production data"
