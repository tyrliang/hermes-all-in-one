# Agent patches

Local fixes to the Hermes Agent tree that ships inside the base image.

## Why this directory exists

`/opt/hermes` comes wholesale from `nousresearch/hermes-agent`. The Dockerfile copies `vendor/hermes-webui` and `vendor/hermes-vault` into the image, but **not** `vendor/hermes-agent` — that tree is a reference-only copy that `scripts/patch-vendor-models.py` reads to keep the WebUI model lists in sync.

A fix committed to `vendor/hermes-agent` therefore changes nothing at runtime. It passes CI, merges, tags, builds a clean image, and the running container still has upstream's version. `apply-agent-patches.sh` closes that gap by installing the patched files over `/opt/hermes` during the build.

## How it works

The Dockerfile copies each patched file out of `vendor/hermes-agent` into `/app/patches/agent/`, keeping the vendored tree as the single source of truth. No second copy to drift. `apply-agent-patches.sh` then installs them and verifies the result.

Every entry in the `PATCHES` table pins **two** sha256 values: the file as it ships in the pinned base image, and our patched version. Both are load-bearing and they catch different failures.

The **base hash** guards the target. If `/opt/hermes` holds something other than the recorded upstream file, `hermes-base` moved, and overwriting would revert whatever upstream changed there.

The **patched hash** guards the source. A vendor refresh — `sync-upstreams.sh`, a subtree pull, or an archive replace — rewrites `vendor/hermes-agent` from upstream and drops the local patch. Without this check the target and source both hold upstream's unpatched file, compare equal, and the script reports `already applied` on a green build with the fix gone. The source is verified *before* any equality shortcut for exactly this reason.

Decision table:

| Condition | Action |
|---|---|
| source ≠ patched hash, source = base hash | **fail** — vendor refresh reverted the patch |
| source ≠ patched hash, source = neither | **fail** — patch edited without updating its hash, or new upstream file |
| target = patched hash | `already applied`, skip |
| target = base hash | install, verify, drop stale bytecode |
| target = neither | **fail** — `hermes-base` moved |

A red build costs minutes. A silent revert costs an outage and a debugging session months later.

Build-log markers, greppable:

```
agent-patch: applied tools/example.py
agent-patch: already applied tools/example.py
agent-patch: FAILED tools/example.py      <- alert
agent-patch: done (0 applied, 0 already present)   <- empty table
```

## Tests

```bash
bash docker/patches/test-apply-agent-patches.sh
```

Covers the upgrade matrix — pristine base, `hermes-base` moved, vendor refresh reverted the patch, both moved, a rebuild of an already-patched image — plus missing source, missing target, and an empty table. The invariant asserted throughout: **the build never goes green with the patch missing from the image.**

The matrix runs against a synthetic patch injected via `PATCHES_OVERRIDE`, so it keeps testing the guard while no real patch is registered. Separately, every row of the real `PATCHES` table is checked against the vendored file it names, which catches a hash left stale after re-basing a patch.

Run it after touching the script or re-basing a patch. Reverting the source verification makes S2 and S3 fail with `SILENT REGRESSION`, which is the bug this guard exists to prevent.

## Current patches

**None.** The table in `apply-agent-patches.sh` is empty as of `hermes-base` `v2026.9.24`.

| File | Fix | Retired |
|------|-----|---------|
| `tools/mcp_tool_transport.py` | MCP HTTP/SSE transports honour `HTTPS_PROXY` / `ALL_PROXY` and the shared `NO_PROXY` rules. Both builders handed httpx an explicit `transport=`, which disables its `trust_env` proxy mounts, so MCP connected direct and every server behind a proxy failed with `[Errno -2] Name or service not known`. | `v2026.9.24` — upstream ships the equivalent fix as `_mcp_proxy_mounts()`, wired into all three MCP client builders via `mounts=`, with a wider matcher (OS proxy, `urllib.request.proxy_bypass`, loopback) and its own test `tests/tools/test_mcp_http_proxy.py` |

Registering a new patch takes two edits: a row in `PATCHES`, and a `COPY vendor/hermes-agent/<path> /app/patches/agent/<path>` in the Dockerfile.

## On a hermes-base bump or a vendor refresh

The build fails with a hash mismatch. That is the system working. Which hash failed tells you what happened:

**"vendored source is UNPATCHED upstream code"** — a vendor refresh reverted `vendor/hermes-agent/<file>`. Re-apply the local patch to that file, commit it, refresh the patched hash, rebuild.

**"base image file does not match the recorded pre-patch hash"** — `hermes-base` moved. Resolve in this order:

1. Diff the new upstream file against the old base version. **Check whether upstream fixed the bug** — if so, drop the patch entirely and delete its row from `PATCHES`.
2. If still needed, re-apply the patch onto the new upstream file and commit it to `vendor/hermes-agent`.
3. Refresh both hashes:

   ```bash
   docker run --rm nousresearch/hermes-agent:<new-tag> \
     sha256sum /opt/hermes/tools/mcp_tool_transport.py     # base hash
   sha256sum vendor/hermes-agent/tools/mcp_tool_transport.py  # patched hash
   ```

4. `bash docker/patches/test-apply-agent-patches.sh`
5. Rebuild and confirm `agent-patch: applied` in the logs.

## Verifying a deployed image

Do not infer from a green build that a patch is live. Check the running container — for example, when `tools/mcp_tool_transport.py` was patched:

```bash
grep -c _env_proxy_for /opt/hermes/tools/mcp_tool_transport.py   # >0 = present
```

With an empty table there is nothing to verify beyond the build log line `agent-patch: done (0 applied, 0 already present)`.
