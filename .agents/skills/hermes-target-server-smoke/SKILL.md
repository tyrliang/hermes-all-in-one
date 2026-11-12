---
name: hermes-target-server-smoke
description: >-
  Validate a candidate hermes-all-in-one Docker image on a target server before
  production rollout. Use after Hermes/WebUI upgrades, before deploying a newly
  built or published image, or when asked to run remote functional acceptance.
  Covers isolated Docker volumes, dedicated Bifrost credentials, Hindsight test-bank
  isolation, real agent tools, restart persistence, and operator handoff.
---

# Hermes target-server smoke

Run the existing `scripts/functional-smoke.py`; do not invent another test harness.
This is an opt-in paid integration test, separate from CI's credential-free
`scripts/smoke.sh`. A pass is evidence for the exact image tested, not permission to
upgrade production. Publishing and deploying remain separately user-gated.

**Location:** `.agents/skills/hermes-target-server-smoke/` (repo-local).
**Working directory:** repository root. Every `scripts/...` command below is relative
**to the repo root**, not this skill directory. Requires local Python 3 stdlib, SSH,
and remote passwordless `sudo docker`; no local Docker image storage is required.

## Safety contract

- Never mount the production volume into a candidate container or change production
  Hermes, its bot credentials, cron jobs, identity, history, or plugin files.
- Use only a named volume labeled `hermes.smoke-test=true`; `--volume` selects it
  independently of the container name. Container names must be `e2e-test` or begin
  `e2e-test-` with a lowercase alphanumeric suffix (hyphens allowed after its first
  character); keep the published port loopback-only. `stop` requires the container's
  same ownership label and removes its inspected ID, never an unrelated name collision.
- Hindsight must use **`hermes-smoke-test-<unique-id>`**, never `personal`, `hermes`,
  `user-richard`, or another production bank. No bank template, additional recall
  banks, or mirrored writes. Do not copy production memories. The runner guards this
  before its backend probes; never bypass those guards to make a run pass.
- Hindsight uses a tenant credential, not bank-scoped server authorization. Bank
  isolation is enforced by fixture configuration/guards. Protect Docker access and
  the credential files accordingly; do not expose them to untrusted callers.
- Secrets stay in root-owned `0600` files on the target host. Never print their values,
  commit them, embed them in an image, or copy production `.env`/vault tokens wholesale.
- No production infrastructure restart, credential rotation, budget increase, or
  deployment unless explicitly authorized. Inspect quota failures rather than retrying
  blindly. Tests make real LLM and Hindsight calls and retain synthetic facts.

## Existing deployment reference (verify live; do not assume immutable)

| Setting | Provisioned value |
|---|---|
| SSH target | `richard@server-elrond` |
| Read-only fixture source | `hermes-personal-richard-hermes-1` |
| Test container | `e2e-test` |
| Test volume | `hermes-smoke-test-managed-data` |
| Port | `127.0.0.1:18789` → container `8787` |
| Hindsight endpoint | `https://ai-memory.liangacy.com` |
| Existing test bank | `hermes-smoke-test-18fc075287a4` |
| Bifrost env file | `/opt/hermes-smoke/bifrost.env` (`BIFROST_API_KEY`) |
| Hindsight env file | `/opt/hermes-smoke/hindsight.env` (`HINDSIGHT_API_KEY`) |
| Bifrost route | `https://bifrost.liangacy.com/openai/v1` |
| Scoped model | `ollama-cloud/deepseek-v4.1-flash:1017` (fixture inherits production model spelling) |
| Dedicated virtual key | `hermes-smoke-test`, UUID `df305c2f-981b-4967-a8a1-d70ef92b9cee` |
| Key limits | $0.10/day; 20 requests/hour; 250,000 tokens/hour |

The durable key and secret references live in `tyrliang/homelab_iac`, not this image
repo (provisioned by PR #461, quota adjustment #462). A runtime-only Bifrost virtual
key can be removed on restart when `source_of_truth: config.json` omits it. Do not
change source-of-truth globally. New durable key provisioning follows that repo's
GitOps/secret conventions and may require a separately approved gateway rollout.

## 1. Select the exact candidate and target

Read `VERSION` and the upgrade PR. Choose a published version/digest or a candidate
image already built **on the target Docker daemon**. Never silently test the runner's
old default image; always pass `--image`. A merge does not publish an image.

```bash
python3 scripts/functional-smoke.py --help
# Set this to the exact candidate being accepted.
IMAGE='ghcr.io/tyrliang/hermes-all-in-one:v0.16.1'
HOST='richard@server-elrond'
NAME='e2e-test'
VOLUME='hermes-smoke-test-managed-data' # preserve the existing fixture and bank
PORT=18789
ssh "$HOST" 'sudo -n docker ps --format "{{.Names}} {{.Image}} {{.Ports}}"; df -h /var/lib/docker'
ssh "$HOST" "sudo -n docker pull '$IMAGE'"
ssh "$HOST" "sudo -n docker image inspect '$IMAGE' --format '{{.Id}} {{json .RepoDigests}}'"
ssh "$HOST" 'sudo -n stat -c "%a %U %n" /opt/hermes-smoke/bifrost.env /opt/hermes-smoke/hindsight.env'
```

Use only trusted image reference strings in shell commands. Record image ID/digest
and host architecture. For a private/unpublished candidate, use its build's exact
remote tag/ID and skip `docker pull`; never rebuild a different commit under the same
name and report it as the published image. The functional runner does not pull/build.

If credentials are missing, inspect available secret-management sources without
printing values. Provision only the scoped test credentials through secure stdin;
never reuse the production Bifrost virtual key. A different host needs its own
root-only credential delivery and SSH/Docker access, not production-volume cloning.

## 2. Reuse or initialize an isolated fixture

Inspect smoke containers and the exact volume first:

```bash
ssh "$HOST" "sudo -n docker ps -a --filter name='$NAME' --format '{{.Names}} {{.Status}}'"
ssh "$HOST" "sudo -n docker volume inspect '$VOLUME'"
```

If the known interactive smoke container is running, stop **only that smoke instance**
before a test; the test creates a fresh container and refuses a name collision:

```bash
python3 scripts/functional-smoke.py stop --host "$HOST" --name "$NAME" --volume "$VOLUME" --image "$IMAGE"
```

Do not run `stop` against an absent container and assume a failure means production
is broken. Verify ownership/name before destructive operations. `stop` removes the
container, not its volume or Hindsight bank.

Only if the fixture volume does not exist:

```bash
python3 scripts/functional-smoke.py init \
  --host "$HOST" --name "$NAME" --volume "$VOLUME" --image "$IMAGE" \
  --source-container hermes-personal-richard-hermes-1
```

`init` reads production source/configuration **read-only** through an allowlisted
exporter. It exports minimal Bifrost routing, local terminal settings, Hindsight
plugin source, and endpoint; it does not export production bank selection or secrets.
It generates a new explicitly labeled bank, seeds a new named volume, records the
plugin source hash, and refuses to overwrite an existing fixture.

For a deliberately refreshed fixture, choose a new `--volume` (and an optional new
`--name`) rather than deleting a working volume. Changing `--name` alone keeps the
same selected volume and bank. If switching hosts, pass that host's actual
`--source-container`.
If production configuration differs from the fixture exporter's Bifrost/Hindsight
schema, investigate and update the exporter intentionally; never copy all config as
a shortcut. Existing volumes are not automatically reseeded after an upstream move.

## 3. Run the complete remote acceptance

```bash
python3 scripts/functional-smoke.py test \
  --host "$HOST" --name "$NAME" --volume "$VOLUME" --port "$PORT" --image "$IMAGE"
```

Require **exit 0 and `[functional-smoke] PASS`**. Preserve the stage output and exact
candidate digest in the PR/release/deployment evidence. The real checks are:

1. WebUI readiness and unauthenticated admin API rejection; no messaging/vault tokens.
2. Hindsight plugin retains a unique synthetic fact and recalls it from the test bank.
3. A real Bifrost-backed Hermes turn writes/reads a unique workspace marker with tools.
4. Container restart preserves that marker in the named volume.
5. Hindsight recalls the fact after restart.
6. A fresh Hermes agent retrieves and reports the exact fact through Hindsight.

The test removes its temporary container on success/failure but preserves its volume
and test bank. `start` is different: it provisions/readies an interactive instance,
**not** the complete functional acceptance. Do not report `start` as a full test pass.
The credential-free gate additionally covers admin login/APIs and lifecycle actions;
run `scripts/smoke.sh` through CI or on a suitable daemon when packaging changes.
Its readiness waits require JSON `status=ok` and `webui.healthy=true`, not HTTP 200 alone.

## 4. Provisioning and failure rules

The runner provisions `pnpm` with PM and synchronizes web/MCP/plugin dependencies as
`hermes`, then uses `pm.environments.project_python` for direct plugin probes. Its
fixture-only dependency overlay retains this image's web packages. This may download
runtime dependencies into the test volume; allow disk/network headroom.

Never install ad hoc packages directly into the sealed `/opt/hermes/.venv`, disable
managed-runtime guards, change install metadata to fake consistency, or run PM as root.
Those shortcuts produced real restart failures during the initial setup. Pass the
selected interpreter's full path as `argv[0]` when executing it; `python` can resolve
the wrong environment. Do not assume that fixed `/opt/hermes/.venv/bin/python` sees
PM-selected plugin dependencies.

| Failure | Action |
|---|---|
| Hindsight 401 | Check target's Hindsight credential delivery; Bifrost key is not Hindsight auth. Never switch to production bank. |
| Bank/multi-bank refusal | Restore safe fixture isolation; never weaken guards. |
| Bifrost quota/rate rejection | Inspect requests, tokens, and dollar counters independently. Normal Hermes context/tool schemas can exceed 50k tokens across two turns. Wait for reset or obtain authorization for changed limits; retain cost/provider bounds. |
| `install out of sync` | Inspect PM-selected environment, ownership and required toolchain. Provision through supported PM APIs; do not bypass guard. |
| WebUI unready | Inspect sanitized container/service logs; HTTP 200 with degraded JSON is failure. |
| Name/port collision | Identify only the smoke-owned resource, stop it or choose a new name/port. Never stop production. |
| Model or plugin incompatibility | Treat as a failed candidate; diagnose/fix and rerun. No fake response, mock backend, or marker-only substitute for real agent behavior. |

No pass proves every provider, plugin, external messaging channel, or production data
migration works. Never claim those unexercised paths. Do not leak credentials in logs
or pasted error payloads. Investigate genuine failures instead of pinning incidental
output/wording tests or retrying until one lucky pass.

## 5. Interactive handoff and cleanup

When requested, leave a separate fresh instance running after a successful test:

```bash
python3 scripts/functional-smoke.py start \
  --host "$HOST" --name "$NAME" --volume "$VOLUME" --port "$PORT" --image "$IMAGE"
ssh -t "$HOST" "sudo -n docker exec -it --user hermes '$NAME' /bin/bash"
```

For browser inspection, forward only the loopback test port:

```bash
ssh -N -L 18789:127.0.0.1:18789 richard@server-elrond
```

Web/admin passwords are generated per container start. Retrieve them privately via an
approved secret-access path if browser login is needed; never paste `docker inspect`
environment output into chat. CLI attachment needs no browser password.

### Take down the container; retain the reusable fixture

After testing, take down the smoke container unless the user requests an interactive
instance be left running. `test` already removes its temporary container automatically;
an instance created with `start` must be removed explicitly:

```bash
# From the repository root, using the same HOST, NAME, VOLUME and IMAGE as the test:
python3 scripts/functional-smoke.py stop \
  --host "$HOST" --name "$NAME" --volume "$VOLUME" --image "$IMAGE"

# Confirm the container is absent and the exact named volume is still present:
ssh "$HOST" "sudo -n docker ps -a --filter name='$NAME' --format '{{.Names}} {{.Status}}'"
ssh "$HOST" "sudo -n docker volume inspect '$VOLUME' --format '{{.Name}} {{json .Labels}}'"
```

`stop` inspects the named container's `hermes.smoke-test=true` ownership label, then
runs `docker rm -f` on that inspected container ID only. It does **not** remove
`$VOLUME`, the Hindsight test bank, or the root-only host credential files.
If the container is already absent after `test`, skip `stop`; still verify the volume.
Never use `docker compose down -v`, `docker volume rm`, or broad prune commands for
normal teardown. Preserve the test bank alongside the volume for reuse.

### Next upgrade: reuse the volume, do not initialize again

Select/pull the next exact candidate as in step 1, then run:

```bash
python3 scripts/functional-smoke.py test \
  --host "$HOST" --name "$NAME" --volume "$VOLUME" --port "$PORT" --image "$IMAGE"
```

Do **not** rerun `init` for the existing volume: the runner mounts the retained fixture,
recreates a fresh container from the new image, and checks persistence and isolated
memory again. Report container absence and retained volume/bank in the handoff.
Delete smoke-owned volumes/banks only on explicit cleanup approval; never delete
production memory. Removing a Docker volume does not remove its Hindsight bank or
revoke credentials.

## Elrond production is not an ordinary Compose image swap

The accepted production container is a custom migration-preserved runtime. Its
host startup guard, acceptance proof, and backup controller pin the exact image
and container identity. The homelab_iac Elrond runbook forbids recreating an accepted
container with `docker compose up` or hand-writing `ready.json`.

Before a production upgrade, audit preserved runtime additions against the new base
and use a reviewed, coordinated upgrade/rollback path for runtime and backup acceptance.
Do not drop the guard or overwrite proof to force a newer image to start.
At the v0.16.1 release, the user explicitly chose to hold production unchanged
pending that upgrade capability; isolated e2e-test success does not lift that hold.

## Delivery checklist

- Exact target, candidate image ID/digest, fixture volume/plugin hash, isolated bank.
- Full functional result and meaningful failed stages if any; CI packaging gate result.
- Running/stopped container state, safe attach/rerun command, credential **paths only**.
- Any infrastructure changes and explicit approval/rollout outcome.
- Production untouched, or exactly which separately approved changes occurred.
- Deploy only on a separate user decision; use `hermes-all-in-one-release` for tagging,
  publishing and curated GitHub notes. Never infer publish/deploy permission from a pass.
