# Agent patches

Local fixes to the Hermes Agent tree that ships inside the base image.

## Why this directory exists

`/opt/hermes` comes wholesale from `nousresearch/hermes-agent`. The Dockerfile copies `vendor/hermes-webui` and `vendor/hermes-vault` into the image, but **not** `vendor/hermes-agent` — that tree is a reference-only copy that `scripts/patch-vendor-models.py` reads to keep the WebUI model lists in sync.

A fix committed to `vendor/hermes-agent` therefore changes nothing at runtime. It passes CI, merges, tags, builds a clean image, and the running container still has upstream's version. `apply-agent-patches.sh` closes that gap by installing the patched files over `/opt/hermes` during the build.

## How it works

The Dockerfile copies each patched file out of `vendor/hermes-agent` into `/app/patches/agent/`, keeping the vendored tree as the single source of truth. No second copy to drift. `apply-agent-patches.sh` then installs them and verifies the result.

Every entry in the `PATCHES` table pins the sha256 of the file **as it ships in the pinned base image** — the pre-patch hash, not the patched one. Before overwriting, the script compares the target against that hash:

- matches the patched file already → `already applied`, skip
- matches the recorded base hash → install the patch, verify, drop stale bytecode
- matches neither → **fail the build**

That last branch is the point. On a `hermes-base` bump, upstream's file changes and the recorded hash stops matching. Pasting our patched copy over it would silently revert whatever upstream changed in that file. A red build is the cheaper outcome.

Build-log markers, greppable:

```
agent-patch: applied tools/mcp_tool_transport.py
agent-patch: already applied tools/mcp_tool_transport.py
agent-patch: FAILED tools/mcp_tool_transport.py      <- alert
```

## Current patches

| File | Fix | Retire when |
|------|-----|-------------|
| `tools/mcp_tool_transport.py` | MCP HTTP/SSE transports honour `HTTPS_PROXY` / `ALL_PROXY` and the shared `NO_PROXY` rules. Both builders hand httpx an explicit `transport=`, which disables its `trust_env` proxy mounts, so MCP connected direct and every server behind a proxy failed with `[Errno -2] Name or service not known`. | `NousResearch/hermes-agent` ships the equivalent fix |

## On a hermes-base bump

The build will fail with a hash mismatch. That is the system working. To resolve:

1. Diff the new upstream file against the old base version. Check whether upstream fixed the bug — if so, drop the patch entirely.
2. If still needed, re-apply the patch onto the new upstream file and commit it to `vendor/hermes-agent`.
3. Refresh the recorded hash:

   ```bash
   docker run --rm nousresearch/hermes-agent:<new-tag> \
     sha256sum /opt/hermes/tools/mcp_tool_transport.py
   ```

4. Rebuild and confirm `agent-patch: applied` in the logs.

## Verifying a deployed image

Do not infer from a green build that the patch is live. Check the running container:

```bash
grep -c _env_proxy_for /opt/hermes/tools/mcp_tool_transport.py   # >0 = present
```
