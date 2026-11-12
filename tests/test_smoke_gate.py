"""Exercise the complete smoke script with local docker/curl process doubles."""

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


SMOKE_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "smoke.sh"

# Only external services are doubled: smoke.sh still runs its real Python
# validators, Bash control flow, login, restart, and cleanup sequence.
STUB_SOURCE = r'''
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

state_path = Path(os.environ["SMOKE_STUB_STATE"])
state = (
    json.loads(state_path.read_text())
    if state_path.exists()
    else {"runs": 0, "running": False}
)
args = sys.argv[1:]
tool = Path(sys.argv[0]).name
with Path(os.environ["SMOKE_STUB_LOG"]).open("a") as log:
    log.write(json.dumps([tool, *args]) + "\n")

if tool == "docker":
    command = args[0]
    if command == "run":
        state["runs"] += 1
        if state["runs"] == int(os.environ.get("SMOKE_STUB_FAIL_RUN", "0")):
            state_path.write_text(json.dumps(state))
            print("simulated docker run failure", file=sys.stderr)
            sys.exit(42)
        state["running"] = True
        print("stub-container-id")
    elif command == "rm":
        state["running"] = False
    elif command == "exec":
        assert state["running"], "exec requires a running container"
        if "sha256sum" in args[-1]:
            assert state.get("signed_in"), "signing key requires admin login"
            print("a" * 64)
    elif command not in ("ps", "logs"):
        raise AssertionError(f"unexpected docker command: {args}")
    state_path.write_text(json.dumps(state))
    sys.exit(0)

assert tool == "curl", tool
assert state["running"], "curl requires a running container"
options = {}
flags_with_value = {
    "-o", "--output", "-w", "--write-out", "-b", "-c", "-X", "--data-urlencode",
}
url = None
iterator = iter(args)
for arg in iterator:
    if arg in flags_with_value:
        options[arg] = next(iterator)
    elif arg.startswith("http://"):
        url = arg
    else:
        assert arg in {"--silent", "--show-error", "--fail", "-sS"}, arg
assert url, args
path = urlsplit(url).path
method = options.get("-X", "GET")
authenticated = "-b" in options and Path(options["-b"]).read_text() == "admin-session"
status = 200
payload = {}
scenario = os.environ.get("SMOKE_STUB_SCENARIO", "healthy")
if path == "/health":
    state["health_probes"] = state.get("health_probes", 0) + 1
    payload = {
        "service": "hermes-control-plane",
        "status": "ok",
        "webui": {
            "healthy": scenario != "health" or state["health_probes"] == 1,
            "running": True,
            "supervisor": "s6",
            "service": "/run/service/hermes-webui",
        },
        "gateway": {"running": False, "healthy": False},
    }
    if (scenario == "webui_restart" and state.get("webui_restart")) or (
        scenario == "gateway_restart" and state.get("gateway_restart")
    ) or (scenario == "container_restart" and state["runs"] > 1):
        payload["status"] = "degraded"
        payload["webui"]["healthy"] = False
elif path == "/admin/login" and method == "POST":
    assert options["--data-urlencode"] == "password=smoke-test-password"
    Path(options["-c"]).write_text("admin-session")
    state["signed_in"] = True
    status = 303
elif path == "/admin":
    status = 303
elif path in {"/", "/login", "/admin/login"}:
    pass
elif path.startswith("/admin/api/"):
    if not authenticated:
        status = 401
    elif path == "/admin/api/status":
        payload = {
            "paths": {
                "config_path": "/opt/data/.hermes/config.yaml",
                "hermes_home": "/opt/data/.hermes",
                "webui_state_dir": "/opt/data/webui",
                "workspace_dir": "/opt/data/workspace",
                "env_path": "/opt/data/.hermes/.env",
            },
            "webui": {"supervisor": "s6", "healthy": True},
            "gateway": {"supervisor": "s6", "autostart_eligible": False},
            "provider_catalog": [{"id": "openrouter", "label": "OpenRouter"}],
        }
        if scenario == "status":
            payload["paths"]["config_path"] = "/wrong/config.yaml"
    elif path == "/admin/api/channels":
        payload = {"ok": scenario != "channels", "values": {}}
    elif path == "/admin/api/pairing/pending":
        payload = {"ok": True, "pending": {} if scenario == "pending" else []}
    elif path == "/admin/api/pairing/approved":
        payload = {"ok": True, "approved": {} if scenario == "approved" else []}
    else:
        assert method == "POST", method
        assert path in {"/admin/api/webui/restart", "/admin/api/gateway/restart"}, path
        state["webui_restart" if "/webui/" in path else "gateway_restart"] = True
        payload = {"ok": True}
else:
    raise AssertionError(f"unexpected URL: {url}")
state_path.write_text(json.dumps(state))
if options.get("-o", options.get("--output")) != "/dev/null":
    print(json.dumps(payload))
if "-w" in options or "--write-out" in options:
    print(status, end="")
'''


@pytest.fixture
def run_smoke(tmp_path: Path):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for name in ("docker", "curl"):
        executable = binaries / name
        executable.write_text(
            f"#!{sys.executable}\n" + textwrap.dedent(STUB_SOURCE), encoding="utf-8"
        )
        executable.chmod(0o755)
    sleeper = binaries / "sleep"
    sleeper.write_text("#!/bin/sh\nexit 0\n")
    sleeper.chmod(0o755)

    def run(scenario="healthy", *, fail_run=0):
        state_path = tmp_path / "state.json"
        log_path = tmp_path / "commands.jsonl"
        environment = {
            **os.environ,
            "PATH": f"{binaries}{os.pathsep}{os.environ['PATH']}",
            "SMOKE_SKIP_BUILD": "1",
            "SMOKE_DATA_DIR": str(tmp_path / "data"),
            "SMOKE_PASSWORD": "smoke-test-password",
            "SMOKE_ADMIN_PASSWORD": "smoke-test-password",
            "SMOKE_STUB_STATE": str(state_path),
            "SMOKE_STUB_LOG": str(log_path),
            "SMOKE_STUB_SCENARIO": scenario,
            "SMOKE_STUB_FAIL_RUN": str(fail_run),
            # Assertion validation must remain enabled even under an optimized
            # Python environment inherited from the pytest launcher.
            "PYTHONOPTIMIZE": "",
        }
        result = subprocess.run(
            ["bash", str(SMOKE_SCRIPT)],
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
        )
        commands = [json.loads(line) for line in log_path.read_text().splitlines()]
        state = json.loads(state_path.read_text())
        assert commands[-1] == ["docker", "rm", "-f", "hermes-control-plane-smoke"]
        assert state["running"] is False
        return result, commands, state

    return run


@pytest.mark.parametrize(
    ("scenario", "reached_stage"),
    [
        ("health", "checking /health payload"),
        ("status", "/health payload OK"),
        ("channels", "admin status paths and supervisors OK"),
        ("pending", "admin status paths and supervisors OK"),
        ("approved", "admin status paths and supervisors OK"),
    ],
)
def test_smoke_rejects_invalid_payload(run_smoke, scenario, reached_stage):
    result, _, _ = run_smoke(scenario)

    assert reached_stage in result.stdout
    assert "AssertionError" in result.stderr, result.stderr
    assert result.returncode != 0, result.stdout
    assert "[smoke] PASS" not in result.stdout
    assert "exercising control-plane actions" not in result.stdout


def test_smoke_healthy_control_completes_full_script(run_smoke):
    result, commands, state = run_smoke()

    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
    assert "[smoke] /health payload OK" in result.stdout
    assert "[smoke] admin status paths and supervisors OK" in result.stdout
    assert "[smoke] admin read-only APIs OK" in result.stdout
    assert result.stdout.splitlines()[-1] == "[smoke] PASS"
    assert state["runs"] == 2
    assert state["signed_in"] is True
    status_requests = [
        command for command in commands
        if command[0] == "curl" and command[-1].endswith("/admin/api/status")
    ]
    assert len(status_requests) == 2
    assert "-b" not in status_requests[0]
    assert "-b" in status_requests[1]
    for service in ("webui", "gateway"):
        assert any(
            command[0] == "curl"
            and "POST" in command
            and any(arg.endswith(f"/admin/api/{service}/restart") for arg in command)
            for command in commands
        )


@pytest.mark.parametrize("failed_run", [1, 2], ids=["startup", "restart"])
def test_smoke_exits_immediately_when_docker_run_fails(run_smoke, failed_run):
    result, commands, state = run_smoke(fail_run=failed_run)

    assert "simulated docker run failure" in result.stderr
    assert result.returncode != 0, result.stdout
    assert "[smoke] PASS" not in result.stdout
    assert state["runs"] == failed_run
    # After run fails, only the EXIT cleanup may execute; polling a stale
    # service or continuing to later checks must not mask launch failure.
    assert commands[-2][:2] == ["docker", "run"]


@pytest.mark.parametrize("scenario", ["webui_restart", "gateway_restart", "container_restart"])
def test_http_200_degraded_after_restart_cannot_pass(run_smoke, scenario):
    result, _, _ = run_smoke(scenario)
    assert "[smoke] /health payload OK" in result.stdout
    assert "exercising control-plane actions" in result.stdout
    assert result.returncode != 0
    assert "timed out waiting for health" in result.stderr
    assert "[smoke] PASS" not in result.stdout
