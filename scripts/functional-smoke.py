#!/usr/bin/env python3
"""Opt-in, credentialed Hermes acceptance on a remote Docker host (stdlib only)."""
import argparse
import json
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import sys
import uuid

PYTHON = "/opt/hermes/.venv/bin/python"


def remote(host, args, data=None, timeout=900):
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", host, shlex.join(args)], input=data, capture_output=True, timeout=timeout)
    if result.returncode:
        detail = (result.stderr + result.stdout).decode(errors="replace")[-4000:]
        detail = re.sub(r"(?:sk-|bf-|hsk_)[A-Za-z0-9_-]{12,}", "<redacted>", detail)
        raise RuntimeError(f"remote command failed ({args[0]}, exit {result.returncode}): {detail}")
    return result.stdout


def docker(args, data=None, timeout=900):
    return remote(options.host, ["sudo", "-n", "docker", *args], data, timeout)


def fixture_operation(request):
    helper = Path(__file__).with_name("functional-volume.py").read_text()
    return remote(options.host, ["sudo", "-n", "python3", "-c", helper], json.dumps(request).encode())


SEED = r'''
import base64,json,pathlib,secrets,sys
x=json.load(sys.stdin); root=pathlib.Path('/opt/data/.hermes')
if (root/'config.yaml').exists(): raise SystemExit('Refusing to overwrite an existing fixture')
root.mkdir(parents=True,exist_ok=True)
(root/'config.yaml').write_text(json.dumps(x['config']))
p=root/'plugins/hindsight'; p.mkdir(parents=True,exist_ok=True)
for name,content in x['plugin_files'].items():
 if pathlib.Path(name).name != name: raise SystemExit('Invalid plugin filename')
 (p/name).write_bytes(base64.b64decode(content))
# Fixture-only dependency overlay keeps the all-in-one web stack in PM's selection.
p=root/'plugins/hindsight/pyproject.toml'
text=p.read_text().replace('dependencies = [', 'dependencies = [\\n    \"PyYAML>=6,<7\", \"uvicorn[standard]==0.54.0\", \"jinja2>=3.1,<4\", \"httpx>=0.27,<1\",',1)
p.write_text(text.replace('\\n', '\n') if 'dependencies = [\\n' in text else text)
p=root/'hindsight'; p.mkdir(exist_ok=True)
(p/'config.json').write_text(json.dumps(x['memory']))
(root/'functional-fixture.json').write_text(json.dumps({'bank':x['memory']['bank_id'],'plugin_sha256':x['plugin_sha256']}))
(root/'.env').write_text('HERMES_ADMIN_PASSWORD='+secrets.token_urlsafe(24)+'\nHERMES_WEBUI_PASSWORD='+secrets.token_urlsafe(24)+'\n')
for p in [root/'config.yaml',root/'.env',root/'hindsight/config.json']: p.chmod(0o600)
import os
for p in [pathlib.Path('/opt/data'), *pathlib.Path('/opt/data').rglob('*')]:os.chown(p,10000,10000)
'''

INSTALL = r'''
import pm
pm.ensure("pnpm", explicit=True)
pm.sync_venv(extras=["web", "mcp"], explicit=True)
'''

MEMORY = r'''
import importlib.util,json,pathlib,sys,time
root=pathlib.Path('/opt/data/.hermes'); cfg=json.loads((root/'hindsight/config.json').read_text())
if not cfg['bank_id'].startswith('hermes-smoke-test-'):raise SystemExit('Refusing non-smoke bank')
if any(cfg.get(k) for k in ('banks','bank_id_template','additional_banks','recall_additional_banks','mirror_to_own_bank')):raise SystemExit('Refusing multi-bank config')
spec=importlib.util.spec_from_file_location('smoke_hindsight',root/'plugins/hindsight/__init__.py',submodule_search_locations=[str(root/'plugins/hindsight')])
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
p=m.HindsightMemoryProvider();p.initialize('functional-smoke')
assert p._bank_id==cfg['bank_id']
try:
 action,topic,code=sys.argv[1:]
 if action=='retain':
  r=json.loads(p.handle_tool_call('hindsight_retain',{'content':f'The isolated Hermes smoke test project {topic} has launch code {code}.','context':'synthetic acceptance fixture'}))
  assert r.get('result')=='Memory stored successfully.',r
 deadline=time.monotonic()+180
 while True:
  r=json.loads(p.handle_tool_call('hindsight_recall',{'query':f'What is the launch code of smoke test project {topic}?'}))
  if code in r.get('result',''):break
  assert time.monotonic()<deadline, 'Hindsight did not recall the synthetic fact'
  time.sleep(3)
 print('PASS: Hindsight '+action+'/recall in isolated bank '+cfg['bank_id'])
finally:p.shutdown()
'''

HEALTH = r'''
import json,time,urllib.request,urllib.error,pathlib
cfg=json.loads(pathlib.Path('/opt/data/.hermes/hindsight/config.json').read_text())
if not cfg.get('bank_id','').startswith('hermes-smoke-test-'):raise SystemExit('Refusing non-smoke memory bank')
if any(cfg.get(k) for k in ('banks','bank_id_template','additional_banks','recall_additional_banks','mirror_to_own_bank')):raise SystemExit('Refusing multi-bank memory configuration')
url='http://127.0.0.1:8787'
for attempt in range(90):
 try:
  with urllib.request.urlopen(url+'/health',timeout=3) as r: data=json.load(r)
  if data.get('status')=='ok' and data['webui']['healthy']:break
 except (OSError,ValueError):pass
 time.sleep(1)
else:raise SystemExit('WebUI did not become ready')
try:
 urllib.request.urlopen(url+'/admin/api/status')
 raise AssertionError('Admin API accepted unauthenticated request')
except urllib.error.HTTPError as e:assert e.code==401
assert not any(k in __import__('os').environ for k in ('DISCORD_BOT_TOKEN','TELEGRAM_BOT_TOKEN','SLACK_BOT_TOKEN','OP_SERVICE_ACCOUNT_TOKEN'))
print('PASS: WebUI readiness, admin auth gate, no bot/vault credentials')
'''


def execute(code, *args):
    launcher = "import os; from pathlib import Path; from pm.environments import project_python; p=str(project_python(Path('/opt/hermes'))); os.execv(p, [p,'-', *__import__('sys').argv[1:]])"
    return docker(["exec", "--user", "hermes", "-i", "-w", "/opt/hermes", options.container_id, PYTHON, "-c", launcher, *args], code.encode()).decode()


def remove_owned_container(identifier):
    metadata = json.loads(docker(["container", "inspect", identifier]))[0]
    if (metadata.get("Config", {}).get("Labels") or {}).get("hermes.smoke-test") != "true":
        raise RuntimeError("Not a smoke-test-owned container")
    # Remove the inspected ID, not a name that could be reassigned before removal.
    docker(["rm", "-f", metadata["Id"]])


def main():
    global options
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "test", "start", "stop"])
    parser.add_argument("--host", default="richard@server-elrond")
    parser.add_argument("--image", default="ghcr.io/tyrliang/hermes-all-in-one:v0.16.2")
    parser.add_argument("--source-container", default="hermes-personal-richard-hermes-1")
    parser.add_argument("--name", default="e2e-test")
    parser.add_argument("--volume", default="hermes-smoke-test-managed-data", help="smoke-owned named volume; independent of the container name")
    parser.add_argument("--key-file", default="/opt/hermes-smoke/bifrost.env", help="root-readable env file on Docker host")
    parser.add_argument("--memory-key-file", default="/opt/hermes-smoke/hindsight.env", help="root-readable Hindsight env file on Docker host")
    parser.add_argument("--port", type=int, default=18789)
    options = parser.parse_args()
    if not re.fullmatch(r"e2e-test(?:-[a-z0-9][a-z0-9-]*)?", options.name):
        parser.error("name must be e2e-test or begin e2e-test- with a lowercase alphanumeric suffix")
    volume = options.volume
    if options.action == "stop":
        remove_owned_container(options.name); return
    if options.action == "init":
        fixture = json.loads(docker(["exec", "-i", options.source_container, PYTHON, "-"], Path(__file__).with_name("functional-fixture.py").read_bytes()))
        bank = "hermes-smoke-test-" + uuid.uuid4().hex[:12]
        fixture["memory"] = {"mode": "local_external", "api_url": fixture.pop("memory_url"), "bank_id": bank, "auto_recall": True, "auto_retain": True, "retain_async": False, "memory_mode": "hybrid", "retain_tags": ["smoke-test"], "recall_tags": ["smoke-test"], "recall_tags_match": "any_strict", "timeout": 120}
        fixture_operation({"action": "init", "volume": volume, "image": options.image,
                           "python": PYTHON, "fixture": fixture, "seed": SEED})
        print(f"Initialized {volume}; isolated Hindsight bank {bank}; plugin SHA256 {fixture['plugin_sha256']}")
        return
    args = ["run", "-d", "--name", options.name, "--label", "hermes.smoke-test=true", "-p", f"127.0.0.1:{options.port}:8787", "--env-file", options.key_file, "--env-file", options.memory_key_file, "-e", "HERMES_ADMIN_PASSWORD="+secrets.token_urlsafe(24), "-e", "HERMES_WEBUI_PASSWORD="+secrets.token_urlsafe(24), "-e", "HERMES_GATEWAY_AUTOSTART=0", "-e", "HERMES_DASHBOARD=0", "-v", volume+":/opt/data", options.image]
    options.container_id = fixture_operation({"action": "run", "volume": volume, "args": args}).decode().strip()
    try:
        print(execute(INSTALL).strip())
        try:
            print(execute(HEALTH).strip())
        except RuntimeError:
            print(docker(["logs", "--tail", "100", options.container_id]).decode(), file=sys.stderr)
            raise
        if options.action == "start":
            print(f"Started {options.name} ({options.container_id}) on {options.host}, loopback port {options.port}; attach using sudo docker exec -it {options.container_id} /bin/bash")
            return
        topic, code = uuid.uuid4().hex, "cobalt-fox-" + secrets.token_hex(6)
        print(execute(MEMORY, "retain", topic, code).strip())
        marker = "workspace-smoke-" + secrets.token_hex(8)
        prompt = f'Use the terminal tool to write exactly {marker} (no newline) into /opt/data/workspace/functional-smoke.txt, then read that file back using a tool. Report the contents. Do not modify anything else.'
        result = docker(["exec", "-w", "/opt/hermes", options.container_id, "/opt/hermes/bin/hermes", "chat", "--oneshot", "-q", prompt], timeout=600).decode()
        actual = execute("from pathlib import Path; print(Path('/opt/data/workspace/functional-smoke.txt').read_text(),end='')")
        if actual != marker or marker not in result: raise RuntimeError("Agent file-tool round trip failed")
        print("PASS: real Bifrost LLM turn and workspace tool round trip")
        docker(["restart", options.container_id])
        print(execute(HEALTH).strip())
        if execute("from pathlib import Path; print(Path('/opt/data/workspace/functional-smoke.txt').read_text(),end='')") != marker: raise RuntimeError("Volume persistence failed")
        print(execute(MEMORY, "recall", topic, code).strip())
        prompt = f'Use hindsight_recall to find the launch code of smoke test project {topic}. Report the exact launch code. Do not guess or write any files.'
        result = docker(["exec", "-w", "/opt/hermes", options.container_id, "/opt/hermes/bin/hermes", "chat", "--oneshot", "-q", prompt], timeout=600).decode()
        if code not in result: raise RuntimeError("Agent did not retrieve the seeded memory after restart")
        print("PASS: real agent Hindsight recall after restart; named-volume persistence")
        print("[functional-smoke] PASS")
    finally:
        if options.action != "start" or sys.exc_info()[0] is not None:
            remove_owned_container(options.container_id)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"[functional-smoke] FAIL: {error}", file=sys.stderr)
        sys.exit(1)
