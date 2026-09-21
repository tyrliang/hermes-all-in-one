---
name: hermes-all-in-one-release
description: >-
  Full hermes-all-in-one release cycle: detect upstream agent/webui/vault tags,
  bump VERSION pins, vendor-replace trees, re-apply local patches, smoke, open
  a detailed PR, merge, tag, watch release.yml, and replace the GitHub Release
  stub with curated notes. Use when the user asks to release, bump Hermes,
  adopt a new agent/webui/vault base, publish an image, write release notes,
  tag v0.x.z, or run the upgrade chore.
---

# hermes-all-in-one Release

End-to-end playbook from real cycles (v0.10.0, v0.11.0, v0.12.0) and maintainer
instructions. Do **not** stop at pin bump + tag — vendor trees, local patches,
detailed PR body, and **edited GitHub Release notes** are required every time.

**Location:** `.agents/skills/hermes-all-in-one-release/` (repo-local only).
Not under `.cursor/skills/` and not installed into `~/.agents/skills`.
Invoke by path: read this `SKILL.md` when releasing.

## Version model

Root `VERSION` (5 fields):

```text
0.12.0
hermes-base=v2026.8.31
agent-base=v2026.8.31
webui-base=v0.52.113
vault-base=v0.25.0
```

| Field | Meaning |
|-------|---------|
| Line 1 `x.y.z` | Package semver → git tag `vX.Y.Z`, GHCR tag |
| `hermes-base` | Docker Hub `nousresearch/hermes-agent` → `Dockerfile` `HERMES_IMAGE` |
| `agent-base` | Vendored `vendor/hermes-agent` tag (usually == hermes-base) |
| `webui-base` | Vendored `vendor/hermes-webui` tag |
| `vault-base` | Vendored `vendor/hermes-vault` tag |

### Version **class** (what kind of semver)

| Change | Semver class | Example |
|--------|--------------|---------|
| `hermes-base` / `agent-base` / `webui-base` advance | **minor** (y+1, z→0) | `0.11.0` → `0.12.0` |
| `vault-base` or any container-only fix/feature | **patch** (z+1) | `0.10.0` → `0.10.1` |
| Breaking packaging (volume/env contract) | **major** (x+1) | rare |

Class ≠ script. `bump-patch.sh` only means “z+1”; it does **not** write
`webui-base` / `vault-base`. Those pins are advanced separately (see below).

### What the scripts actually do

| Script / helper | Writes |
|-----------------|--------|
| `./scripts/bump-hermes.sh <tag>` | package y+1/z=0, `hermes-base`, `agent-base`, Dockerfile `HERMES_IMAGE` |
| `./scripts/bump-patch.sh` | package z+1 only; **preserves** all `*_base` lines unchanged |
| `./scripts/set-version.sh X.Y.Z [hermes-tag]` | explicit package (+ optional hermes pin/Dockerfile) |
| `pin_webui_base` / `pin_vault_base` / `pin_agent_base` in `scripts/version-lib.sh` | one pin line each |
| `.github/workflows/sync-upstreams.yml` | **only** automation that calls `pin_webui_base` / `pin_vault_base` today |

`write_version_file()` re-reads and **preserves** `agent-base` / `webui-base` /
`vault-base`; it never advances them.

**Local webui-only bump (minor class):**

```bash
. scripts/version-lib.sh
read_version_file .
# set minor package version explicitly, e.g. 0.13.0
./scripts/set-version.sh 0.13.0          # keeps hermes-base; does not touch webui
pin_webui_base "v0.52.200"               # advances webui-base
# then vendor webui + patch-vendor-models.py + smoke
```

**Local vault-only bump (patch class):**

```bash
. scripts/version-lib.sh
read_version_file .
pin_vault_base "v0.26.0"
./scripts/bump-patch.sh                  # z+1; preserves the new vault-base
# vendor vault, re-apply #42, smoke
```

Or hand-edit the `webui-base=` / `vault-base=` line in `VERSION`, then run the
matching semver script.

Pushing to `main` publishes **nothing**. Only `git push origin vX.Y.Z` triggers
`.github/workflows/release.yml`.

## Hard requirements (every cycle)

From maintainer sessions — acceptance criteria:

1. **Check all three upstreams** (agent, webui, vault), not only Hermes.
2. **Vendor the trees** that moved — pin-only `check-upstream` PRs are incomplete.
3. **Diff pre-replace vs old upstream tag** so local patches are not lost.
4. **Re-apply local patches** after every relevant vendor replace.
5. **Run `./scripts/smoke.sh`** when vendor or Dockerfile changed.
6. **PR body is the release draft** — pin table, layer changes, curated upstream
   feat/fix delta, test plan. Rewrite thin automation stubs.
7. **After tag + `release.yml` green**, **`gh release edit`** full notes —
   workflow only writes a 2-line stub and will **not** overwrite an existing body.
8. **Assistant**: explicit-path commits, push, open/update PR. Merge when user
   says. Tag + release notes when asked to publish.

### Literal user arcs (source sessions)

| Session | User steps |
|---------|------------|
| v0.10.0 / PR #53 (`2026-08-17…01a0107a`) | Update agent to target tag; check webui; bump + prepare release → write release note with feat/fix delta vs hermes-agent (and any other pin diff) → merge PR then publish steps |
| v0.11.0 / PR #58 (`chore-upgrade…01a0452c`) | Look for upstream agent/webui/etc.; latest; tests; PR; prepare bump → merge, tag, push, watch CI → write release note; confirm which skill to invoke next time |
| Retro notes (`2026-07-31…019fb9b3`) | After merge, do planned publish work; retroactively write proper GitHub notes for prior tags so deltas are knowable later |

## Local patches registry

| Area | What | When |
|------|------|------|
| **Agent `mcp_tool_transport.py`** | MCP HTTP/SSE transports honour `HTTPS_PROXY`/`ALL_PROXY` + shared `NO_PROXY`. Upstream hands httpx an explicit `transport=`, killing `trust_env` proxy mounts — every MCP server behind a proxy fails `[Errno -2]`. | **Every** `vendor/hermes-agent` replace until upstream ships it. Re-apply to the vendored file, then refresh **both** hashes in `docker/patches/apply-agent-patches.sh` |
| Vault `#42` | `_AnyNameTemplate` in vault `service_ids.py` (+ test) so custom env names work (e.g. `HINDSIGHT_API_KEY=hv://hindsight`) | **Every** `vendor/hermes-vault` replace until upstream ships it |
| WebUI models | `python3 scripts/patch-vendor-models.py` | After agent and/or webui vendor change |
| Upstream junk | Strip accidental paths (e.g. `apps/desktop/'/var/folders/...` mutex files) | After agent archive replace if present |

Before replace: diff `vendor/<name>` against the **old** pin tag; list runtime
deltas; replace; re-apply; targeted tests.

### Agent-tree patches are not shipped by the vendor copy

`vendor/hermes-agent` is **reference-only** — the Dockerfile never copies it.
`/opt/hermes` comes wholesale from the `nousresearch/hermes-agent` base image.
A fix committed to that tree ships nothing until `docker/patches/apply-agent-patches.sh`
installs it over `/opt/hermes` at build time. This cost a full release cycle
(v0.14.1 tagged, built, and published with no behavioural change).

That script pins the base **and** patched hash per file and fails the build on
either mismatch, so a vendor refresh that reverts a patch is a red build rather
than a silent revert. After any agent vendor change:

```bash
bash docker/patches/test-apply-agent-patches.sh
```

and confirm `agent-patch: applied <path>` in the smoke build log. A green build
alone does **not** prove an agent-level patch reached the image — verify on the
running container:

```bash
grep -c _env_proxy_for /opt/hermes/tools/mcp_tool_transport.py   # non-zero
```

## Vendor strategy

Prefer `./scripts/sync-upstreams.sh` (subtree pull for **agent + webui only**;
clean tree required; does **not** vendor vault or write pins).

When subtree is unmergeable (common across large tag gaps):

```bash
TAG=v2026.8.31
OLD_TAG=$(sed -n 's/^agent-base=//p' VERSION)   # pin currently in tree
# Tags land in refs/tags/, not refs/remotes/<remote>/$TAG.
git fetch hermes-agent-upstream tag "$TAG" tag "$OLD_TAG"
# Pre-replace: MUST resolve the old pin to a real tree (not an empty dir).
#   tmp=$(mktemp -d) && git archive "$OLD_TAG" | tar -x -C "$tmp"
#   diff -rq "$tmp" vendor/hermes-agent | grep ' differ$'   # local patches
#   rm -rf "$tmp"
rm -rf vendor/hermes-agent
mkdir -p vendor/hermes-agent
git archive "$TAG" | tar -x -C vendor/hermes-agent
# strip junk, re-apply patches
python3 scripts/patch-vendor-models.py   # gate: OpenRouter/Codex counts must be non-zero
git add vendor/hermes-agent   # explicit paths
```

Same pattern for webui/vault with their remotes. Commit message must note
archive-replace + re-applied patches.

Remotes (create if missing):

- `hermes-agent-upstream` → `https://github.com/NousResearch/hermes-agent.git`
- `hermes-webui-upstream` → `https://github.com/nesquena/hermes-webui.git`
- vault → `https://github.com/asimons81/hermes-vault.git`

## Command cheat sheet

```bash
./scripts/read-version.sh
cat VERSION
./scripts/latest-hermes-tag.sh

./scripts/bump-hermes.sh v2026.9.7      # hermes/agent minor + Dockerfile
./scripts/bump-patch.sh                 # z+1 only; does not pin webui/vault
./scripts/set-version.sh 0.12.1 [tag]

# webui/vault pins (no dedicated bump-*.sh):
. scripts/version-lib.sh && read_version_file .
pin_webui_base "v0.52.200"
pin_vault_base "v0.26.0"

./scripts/sync-upstreams.sh
python3 scripts/patch-vendor-models.py
./scripts/smoke.sh
```

Detect other upstreams:

```bash
gh api repos/nesquena/hermes-webui/tags --jq '.[].name' | head -20
gh api repos/asimons81/hermes-vault/releases --jq '.[].tag_name' | head -10
gh api repos/NousResearch/hermes-agent/releases --jq '.[:5]|.[]|{tag:.tag_name,name:.name}'
```

Skip experimental WebUI tags (`exp-*`) unless the user explicitly wants them.

## Full cycle checklist

```
### 0. Orient
- [ ] Read VERSION + origin/main VERSION
- [ ] Read this skill (`.agents/skills/hermes-all-in-one-release/SKILL.md`)
- [ ] git fetch origin --tags --prune
- [ ] Clean branch from main (or adopt existing chore/bump-*)

### 1. Detect upstreams
- [ ] hermes-agent vs hermes-base / agent-base
- [ ] stable hermes-webui vs webui-base (ignore exp-*)
- [ ] hermes-vault vs vault-base
- [ ] Decide minor vs patch vs multi-pin; which scripts + pin_* calls

### 2. Branch + pins
- [ ] Branch: chore/bump-hermes-<tag> or chore/release-vX.Y.Z
- [ ] If check-upstream PR exists: checkout it; do not leave pin-only
- [ ] bump-hermes / bump-patch / set-version + pin_webui_base / pin_vault_base as needed
- [ ] Dockerfile HERMES_IMAGE matches hermes-base when hermes moved

### 3. Vendor
- [ ] Each moved pin: subtree or archive-replace
- [ ] Pre-replace diff vs old pin → local patches list
- [ ] Re-apply patches (**agent mcp_tool_transport.py**, vault #42, etc.)
- [ ] Agent vendor changed → refresh both hashes in `docker/patches/apply-agent-patches.sh`
- [ ] patch-vendor-models.py after agent/webui vendor
- [ ] Strip upstream junk if present
- [ ] README VERSION example matches pins

### 4. Verify
- [ ] ./scripts/smoke.sh PASS (or document skip)
- [ ] `bash docker/patches/test-apply-agent-patches.sh` PASS (if agent patches exist)
- [ ] Smoke log shows `agent-patch: applied <path>` for every registered patch
- [ ] Vault patch: pytest vendor/hermes-vault/tests/test_service_ids.py
- [ ] Optional compileall on touched vendor trees

### 5. PR
- [ ] git add <specific paths> only
- [ ] chore(release): / chore(sync): commit messages
- [ ] Push as human user (not github-actions[bot])
- [ ] Open/update PR; rewrite body (template) — never leave automation stub
- [ ] Required checks: vendor syntax + smoke
- [ ] action_required / 0 jobs → re-run workflow

### 6. Merge (user gate unless told to merge)
- [ ] Merge when user says; else leave for user
- [ ] git checkout main && git pull
- [ ] Confirm VERSION on main

### 7. Tag
- [ ] Tag == VERSION line 1 with v prefix
- [ ] Drop colliding local tags from other repos if needed
- [ ] git tag vX.Y.Z && git push origin vX.Y.Z
- [ ] Never docker push GHCR manually

### 8. Watch release.yml
- [ ] preflight → amd64 + arm64 → manifest → :vX.Y.Z + :latest
- [ ] Stub GitHub Release created

### 9. Release notes (REQUIRED)
- [ ] After release.yml green:
      gh release edit "vX.Y.Z" --title "hermes-all-in-one vX.Y.Z" --notes-file /tmp/notes.md
- [ ] Pin table, layer changes, upstream deltas, upgrade, verification
- [ ] Do not pre-create a --draft release (workflow sees draft via
      `gh release view` and skips create → release stays unpublished forever)
```

## PR body template

Model after PRs #53, #58, #59.

```markdown
## Summary

Upstream refresh and release prep for **hermes-all-in-one vX.Y.Z**.

| Pin | Was (main / vOLD) | Now |
|-----|-------------------|-----|
| package | … | **X.Y.Z** (minor|patch: reason) |
| hermes-base / agent-base | … (Agent v…) | **…** |
| webui-base | … | … |
| vault-base | … | … |

### Changes in this PR
- Dockerfile / VERSION pins
- Vendor method (subtree vs archive) + re-applied patches
- patch-vendor-models / layer fixes
- README VERSION example

### Other upstreams checked
- hermes-webui: …
- hermes-vault: …

---

## Upstream delta: Hermes Agent vA → vB

**Window:** [compare URL] · stats

Link upstream releases. Curate gateway/container-relevant highlights
(not a raw dump).

### Features / fixes / security / container operators / not shipping

## Vault / WebUI sections (if pins moved; else “held at …”)

## Test plan
- [x] local smoke / targeted pytest
- [ ] CI vendor-syntax + smoke green
- [ ] After merge: `git tag vX.Y.Z && git push origin vX.Y.Z`

## Release notes sketch
Seed paragraph for step 9.
```

## GitHub Release notes

`release.yml` stub:

```text
Built on Hermes Agent **${HERMES_BASE}**.

Image: `ghcr.io/<owner>/hermes-all-in-one:vX.Y.Z`
```

If a release already exists for the tag, create is skipped and the body is
**never** auto-updated. Always edit after green:

```bash
gh release edit "vX.Y.Z" --title "hermes-all-in-one vX.Y.Z" --notes-file /tmp/release-vX.Y.Z.md
```

Body structure (see published v0.11.0 / v0.12.0):

1. Summary + pin table + image + compare URL  
2. Layer changes (this repo)  
3. Upstream delta per moved component (curated)  
4. Upgrade (`docker pull`, env contract)  
5. Verification (PR CI, main CI, release jobs)

## Agent instructions (ordered)

1. Read `VERSION`; classify Hermes vs webui vs vault vs layer-only.
2. Detect latest tags for all three; report moves vs holds.
3. Use scripts + `pin_*` correctly — do not claim `bump-patch` advances webui/vault.
4. Vendor every moved pin; archive-replace if subtree fails; diff + re-apply.
5. `patch-vendor-models.py` after agent/webui vendor changes.
6. README VERSION example matches.
7. `./scripts/smoke.sh` before merge/tag confidence.
8. PR with full body; explicit path staging.
9. Merge only if asked; then pull main, tag, push tag.
10. Watch `release.yml` green.
11. **`gh release edit`** full notes. Never leave the stub.
12. Summarize: pins, PR URL, tag, image, release URL.

**Commit messages:** `chore(release): 0.12.0 on hermes v…` · `chore(sync): vendor …` · `fix(scope): …` + patch bump.

## Automation vs ad-hoc

| What | How |
|------|-----|
| New Hermes on Docker Hub | `check-upstream.yml` → often **pin-only** PR — still vendor + notes |
| Vendor subtree | `sync-upstreams.yml` or `scripts/sync-upstreams.sh` |
| PR validation | `ci.yml`: **vendor syntax** + **smoke** |
| Publish image + stub Release | Tag `vX.Y.Z` → `release.yml` |
| Curated notes | **Manual** `gh release edit` |

Bot PRs may stall (`action_required`). Prefer human-user push.

## Troubleshooting

| Issue | Action |
|-------|--------|
| `bump-hermes` no-op | Already on that hermes-base |
| Subtree unmergeable | Archive-replace after local-patch diff |
| Vault custom env broken | Re-apply #42 |
| Smoke apt fail (macOS) | `docker build --network=host` then `SMOKE_SKIP_BUILD=1 ./scripts/smoke.sh` |
| Release preflight fail | Tag must match VERSION line 1 |
| Notes still stub | `gh release edit` after green |
| Draft release stuck unpublished | Never pre-create `--draft`; edit after workflow create |
| Local tag collision | `git tag -d vX.Y.Z` if unrelated SHA; retag |
| Skill not found | Open `.agents/skills/hermes-all-in-one-release/SKILL.md` in-repo (not global) |

## More detail

- [README.md § Releases & versioning](../../../README.md#releases--versioning)
- [examples.md](examples.md)
