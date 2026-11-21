"""Exercise host-side fixture transactions without Docker or shared lock paths."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import threading
import uuid

import pytest


spec = importlib.util.spec_from_file_location(
    "functional_volume", Path(__file__).resolve().parents[1] / "scripts/functional-volume.py"
)
volume_helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(volume_helper)

OWNED = {"hermes.smoke-test": "true"}
NO_RACE = object()
SEED = """
import json
from pathlib import Path
import sys
Path('/opt/data/fixture.json').write_text(json.dumps(json.load(sys.stdin)))
"""


class DockerState:
    """Model Docker's persistent volumes, attachments, and idempotent create."""

    def __init__(self, root):
        self.root = root
        self.volumes = {}
        self.containers = {}
        self.mounts = []
        self.race_labels = NO_RACE
        self.fail_next_run = False
        self.created_labels = []

    def add_volume(self, name, labels):
        path = self.root / name
        path.mkdir(parents=True)
        self.volumes[name] = {"Name": name, "Driver": "local", "Labels": labels}
        return path

    def add_container(self, name, volume, status):
        self.containers[name] = {"Id": uuid.uuid4().hex, "volume": volume, "status": status}

    def docker(self, args, data=None):
        if args[:2] == ["volume", "ls"]:
            return "\n".join(self.volumes).encode()
        if args[:2] == ["volume", "inspect"]:
            name = args[-1]
            if name not in self.volumes:
                raise RuntimeError("No such volume: " + name)
            return json.dumps([self.volumes[name]]).encode()
        if args[:2] == ["volume", "create"]:
            name = args[-1]
            labels = dict(args[index + 1].split("=", 1) for index, arg in enumerate(args) if arg == "--label")
            self.created_labels.append(labels)
            if self.race_labels is not NO_RACE:
                self.add_volume(name, self.race_labels)
                (self.root / name / "sentinel").write_bytes(b"not a fixture")
                self.race_labels = NO_RACE
            # Docker accepts an existing same-driver name without changing labels.
            if name not in self.volumes:
                self.add_volume(name, labels)
            return (name + "\n").encode()
        if args[:2] == ["container", "ls"]:
            assert "--all" in args, "Stopped containers retain their volume attachment"
            selected = args[args.index("--filter") + 1].removeprefix("volume=")
            return "\n".join(c["Id"] for c in self.containers.values() if c["volume"] == selected).encode()
        if args[0] == "run":
            if self.fail_next_run:
                self.fail_next_run = False
                raise RuntimeError("Docker failed before creating a container")
            selected = args[args.index("-v") + 1].split(":", 1)[0]
            assert selected in self.volumes
            self.mounts.append(selected)
            if "--rm" in args:
                code = args[args.index("-c") + 1].replace("/opt/data", str(self.root / selected))
                result = subprocess.run(
                    [sys.executable, "-c", code], input=data, capture_output=True, timeout=10
                )
                if result.returncode:
                    raise RuntimeError(result.stderr.decode())
                return result.stdout
            name = args[args.index("--name") + 1]
            if name in self.containers:
                raise RuntimeError("Container name already exists")
            self.add_container(name, selected, "running")
            return self.containers[name]["Id"].encode()
        raise AssertionError(f"Unexpected Docker mutation or command: {args!r}")


@pytest.fixture
def backend(monkeypatch, tmp_path):
    state = DockerState(tmp_path / "volumes")
    monkeypatch.setattr(volume_helper, "LOCK_ROOT", tmp_path / "locks")
    monkeypatch.setattr(volume_helper, "docker", state.docker)
    return state


def init_request(volume="fixture"):
    return {
        "action": "init", "volume": volume, "image": "fixture-image",
        "python": "/opt/hermes/.venv/bin/python", "seed": SEED,
        "fixture": {"config": {"model": "fixture-model"}, "memory": {"bank_id": "hermes-smoke-test-isolated"}},
    }


def run_request(volume="fixture", name="e2e-test"):
    return {
        "action": "run", "volume": volume,
        "args": ["run", "-d", "--name", name, "-v", volume + ":/opt/data", "fixture-image"],
    }


@pytest.mark.parametrize("raced_labels", [
    None,
    {"hermes.smoke-test": "false"},
    {"hermes.smoke-test": "true", "hermes.smoke-test.init-id": "another-creator"},
])
def test_init_never_mounts_same_driver_volume_created_after_census(backend, raced_labels):
    backend.race_labels = raced_labels

    with pytest.raises(RuntimeError):
        volume_helper.run(init_request())

    assert backend.volumes["fixture"] == {"Name": "fixture", "Driver": "local", "Labels": raced_labels}
    assert list((backend.root / "fixture").iterdir()) == [backend.root / "fixture/sentinel"]
    assert (backend.root / "fixture/sentinel").read_bytes() == b"not a fixture"
    assert backend.mounts == []
    assert backend.containers == {}


def test_init_seeds_only_its_proven_owned_volume(backend):
    requests = [init_request(), init_request("second-fixture")]

    for request in requests:
        volume_helper.run(request)
        name = request["volume"]
        labels = backend.volumes[name]["Labels"]
        assert labels["hermes.smoke-test"] == "true"
        uuid.UUID(labels["hermes.smoke-test.init-id"])
        assert json.loads((backend.root / name / "fixture.json").read_text()) == request["fixture"]

    labels = [backend.volumes[request["volume"]]["Labels"] for request in requests]
    assert labels == backend.created_labels
    assert labels[0]["hermes.smoke-test.init-id"] != labels[1]["hermes.smoke-test.init-id"]
    assert backend.mounts == ["fixture", "second-fixture"]
    assert backend.containers == {}


@pytest.mark.parametrize("action", ["init", "run"])
def test_transaction_keeps_real_lock_until_docker_mount(monkeypatch, backend, action):
    if action == "run":
        backend.add_volume("fixture", OWNED)

    def docker(args, data=None):
        if args[0] == "run":
            with pytest.raises(RuntimeError, match="transaction already in progress"):
                with volume_helper.volume_lock("fixture"):
                    pytest.fail("Fixture mount must remain inside the transaction lock")
        return backend.docker(args, data)

    monkeypatch.setattr(volume_helper, "docker", docker)
    volume_helper.run(init_request() if action == "init" else run_request())

    assert backend.mounts == ["fixture"]


@pytest.mark.parametrize("labels", [None, OWNED])
def test_init_refuses_preexisting_volume_without_touching_it(backend, labels):
    path = backend.add_volume("fixture", labels)
    (path / "sentinel").write_bytes(b"existing data")

    with pytest.raises(RuntimeError):
        volume_helper.run(init_request())

    assert backend.created_labels == []
    assert backend.volumes["fixture"]["Labels"] == labels
    assert (path / "sentinel").read_bytes() == b"existing data"
    assert list(path.iterdir()) == [path / "sentinel"]
    assert backend.mounts == []


@pytest.mark.parametrize("status", ["running", "exited"])
def test_run_refuses_volume_with_any_existing_consumer(backend, status):
    backend.add_volume("fixture", OWNED)
    backend.add_container("previous-fixture", "fixture", status)
    before = dict(backend.containers)

    with pytest.raises(RuntimeError):
        volume_helper.run(run_request(name="e2e-test-new"))

    assert backend.containers == before
    assert "e2e-test-new" not in backend.containers
    assert backend.mounts == []


@pytest.mark.parametrize("labels", [None, {}, {"hermes.smoke-test": "false"}])
def test_run_refuses_unowned_volume_without_creating_container(backend, labels):
    backend.add_volume("fixture", labels)

    with pytest.raises(RuntimeError):
        volume_helper.run(run_request())

    assert backend.volumes["fixture"]["Labels"] == labels
    assert backend.containers == {}
    assert backend.mounts == []


def test_idle_retained_fixture_without_init_id_can_run_and_holds_attachment_lease(backend):
    backend.add_volume("fixture", OWNED)

    container_id = volume_helper.run(run_request())

    assert container_id == backend.containers["e2e-test"]["Id"].encode()
    assert backend.containers["e2e-test"]["volume"] == "fixture"
    assert backend.containers["e2e-test"]["status"] == "running"
    assert backend.volumes["fixture"]["Labels"] == OWNED
    # The operation lock is gone, but the new container is the ongoing lease.
    with pytest.raises(RuntimeError):
        volume_helper.run(run_request(name="e2e-test-second"))
    assert set(backend.containers) == {"e2e-test"}
    assert backend.mounts == ["fixture"]


def test_real_flock_refuses_concurrent_operation_before_docker(monkeypatch, backend):
    acquired = threading.Event()
    release = threading.Event()
    errors = []

    def hold_lock():
        try:
            with volume_helper.volume_lock("fixture"):
                acquired.set()
                if not release.wait(10):
                    raise RuntimeError("Timed out waiting to release the test lock")
        except BaseException as error:
            errors.append(error)
            acquired.set()

    def unexpected_docker(*args, **kwargs):
        pytest.fail("A blocked transaction must not reach Docker")

    monkeypatch.setattr(volume_helper, "docker", unexpected_docker)
    holder = threading.Thread(target=hold_lock)
    holder.start()
    try:
        assert acquired.wait(5), "Lock holder did not start"
        assert not errors
        with pytest.raises(RuntimeError):
            volume_helper.run(run_request())
    finally:
        release.set()
        holder.join(timeout=5)
    assert not holder.is_alive()
    assert not errors
    monkeypatch.setattr(volume_helper, "docker", backend.docker)
    backend.add_volume("fixture", OWNED)
    volume_helper.run(run_request())
    assert "e2e-test" in backend.containers


def test_real_flock_releases_after_docker_error_without_removing_volume(backend):
    path = backend.add_volume("fixture", OWNED)
    (path / "sentinel").write_bytes(b"retained fixture")
    backend.fail_next_run = True

    with pytest.raises(RuntimeError, match="Docker failed"):
        volume_helper.run(run_request())

    assert backend.volumes["fixture"]["Labels"] == OWNED
    assert (path / "sentinel").read_bytes() == b"retained fixture"
    assert backend.containers == {}
    volume_helper.run(run_request())
    assert backend.containers["e2e-test"]["volume"] == "fixture"
