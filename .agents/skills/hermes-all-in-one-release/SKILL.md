---
name: hermes-all-in-one-release
description: >-
  Full hermes-all-in-one release cycle: detect upstream Hermes and stable WebUI
  tags, bump VERSION pins, smoke, open a detailed PR, merge, tag, watch
  release.yml, and replace the GitHub Release stub with curated notes. Use when
  the user asks to release, bump Hermes, adopt a new agent or webui base,
  publish an image, write release notes, tag v0.x.z, or run the upgrade chore.
---

# hermes-all-in-one Release

End-to-end playbook. Do **not** stop at pin bump + tag — a detailed PR body and
**edited GitHub Release notes** are required every time. Do **not** vendor
upstream trees. Do **not** re-add Hermes Vault.

**Location:** `.agents/skills/hermes-all-in-one-release/` (repo-local only).
Not under `.cursor/skills/` and not installed into `~/.agents/skills`.
Invoke by path: read this `SKILL.md` when releasing.

## Version model

Root `VERSION`:

```text
0.16.1
hermes-base=v0.23.1
webui-base=v0.52.544
webui-sha=687d80333870c3797d6858738621fca13d1bf27a
```

| Field | Meaning |
|-------|---------|
| Line 1 `x.y.z` | Package semver → git tag `vX.Y.Z`, GHCR tag |
| `hermes-base` | Docker Hub `nousresearch/hermes-agent` → `Dockerfile` `HERMES_IMAGE` |
| `webui-base` | Human label for the WebUI release |
| `webui-sha` | Commit the image fetches. Not the tag. |

There is no `vendor/` tree and no Vault. Do not archive-replace a vendor tree. Do not re-add Vault.
Agent bytes are the base image. WebUI bytes are
`https://github.com/nesquena/hermes-webui/archive/<webui-sha>.tar.gz`.

### Version **class** (what kind of semver)

| Change | Semver class | Example |
|--------|--------------|---------|
| `hermes-base` or `webui-base` advance | **minor** (y+1, z→0) | `0.14.3` → `0.15.0` |
| container-only fix/feature | **patch** (z+1) | `0.15.0` → `0.15.1` |
| Breaking packaging (volume/env contract) | **major** (x+1) | rare; Vault left in unreleased 0.15.0 by maintainer call |

`bump-patch.sh` only means z+1. It does not write `webui-base` or `webui-sha`.

### What the scripts actually do

| Script / helper | Writes |
|-----------------|--------|
| `./scripts/bump-hermes.sh <tag>` | package y+1/z=0, `hermes-base`, Dockerfile `HERMES_IMAGE` |
| `./scripts/bump-patch.sh` | package z+1 only; preserves `webui-base` and `webui-sha` |
| `./scripts/set-version.sh X.Y.Z [hermes-tag]` | explicit package (+ optional hermes pin/Dockerfile) |
| `pin_webui_base` / `pin_webui_sha` in `scripts/version-lib.sh` | one pin line each |
| `./scripts/sync-upstreams.sh` | resolves `webui-base` to `webui-sha`. Does not vendor |
| `.github/workflows/sync-upstreams.yml` | opens a PR that advances those two WebUI pins |

`write_version_file()` preserves `webui-base` and `webui-sha`. It does not write `agent-base` or `vault-base`. Those helpers are gone.

**WebUI pin move (minor class if that is the only upstream move, else ride the Hermes minor):**

```bash
. scripts/version-lib.sh
read_version_file .
pin_webui_base "v0.52.200"
./scripts/sync-upstreams.sh          # writes webui-sha from the tag
# Dockerfile reads webui-sha from VERSION. No vendor tree. Smoke.
```

Pushing to `main` publishes **nothing**. Only `git push origin vX.Y.Z` triggers
`.github/workflows/release.yml`.

## Hard requirements (every cycle)

1. **Check Hermes and stable WebUI** (ignore `exp-*`). Vault is not installed. Do not re-add it.
2. **Do not vendor.** A pin-only Hermes PR is complete once `HERMES_IMAGE` matches `hermes-base`. A WebUI move is `webui-base` plus `webui-sha`. The image fetches that commit from `VERSION`.
3. **Run `./scripts/smoke.sh`** when Dockerfile or VERSION pins changed.
4. **PR body is the release draft** — pin table, layer changes, curated upstream feat/fix delta, test plan. Rewrite thin automation stubs.
5. **After tag + `release.yml` green**, **`gh release edit`** full notes. The workflow stub will not overwrite an existing body.
6. **Assistant**: explicit-path commits, push, open/update PR. Merge when user says. Tag + release notes when asked to publish.

Pushing to `main` publishes **nothing**. Only `git push origin vX.Y.Z` triggers
`.github/workflows/release.yml`.


### Literal user arcs (source sessions)

| Session | User steps |
|---------|------------|
| v0.10.0 / PR #53 (`2026-08-17…01a0107a`) | Update agent to target tag; check webui; bump + prepare release → write release note with feat/fix delta vs hermes-agent (and any other pin diff) → merge PR then publish steps |
| v0.11.0 / PR #58 (`chore-upgrade…01a0452c`) | Look for upstream agent/webui/etc.; latest; tests; PR; prepare bump → merge, tag, push, watch CI → write release note; confirm which skill to invoke next time |
| Retro notes (`2026-07-31…019fb9b3`) | After merge, do planned publish work; retroactively write proper GitHub notes for prior tags so deltas are knowable later |

## Local patches registry

| Area | What | When |
|------|------|------|
| WebUI models | `scripts/patch-vendor-models.py` inside the image build, reading `/opt/hermes` | Every image build. Do not commit a patched WebUI tree |

Vault is not installed. Do not re-apply patch #42. Do not diff a `vendor/` tree; there is not one.

### Agent-tree patches are not shipped by the vendor copy

`vendor/hermes-agent` is **reference-only** — the Dockerfile never copies it.
`/opt/hermes` comes wholesale from the `nousresearch/hermes-agent` base image.
A fix committed to that tree ships nothing until `docker/patches/apply-agent-patches.sh`
installs it over `/opt/hermes` at build time. This cost a full release cycle
(v0.14.1 tagged, built, and published with no behavioural change).

That script pins the base **and** patched hash per file and fails the build on
either mismatch, so a vendor refresh that reverts a patch is a red build rather
than a silent revert. The table is currently empty, so the build step is a no-op
(`agent-patch: done (0 applied, 0 already present)`); the harness stays tested
against a synthetic patch. After any agent vendor change:

```bash
bash docker/patches/test-apply-agent-patches.sh
```

A green build alone does **not** prove an agent-level patch reached the image —
when the table is non-empty, confirm `agent-patch: applied <path>` in the smoke
build log and verify the marker on the running container, e.g.:

```bash
grep -c _mcp_proxy_mounts /opt/hermes/tools/mcp_tool_transport.py   # non-zero
```

## Fetch strategy

Do not vendor. Do not `git subtree pull`. Do not `git archive` into `vendor/`.

- Agent: `./scripts/bump-hermes.sh <tag>` writes `hermes-base` and `Dockerfile` `HERMES_IMAGE`.
- WebUI: set `webui-base` to the stable tag (ignore `exp-*`), then `./scripts/sync-upstreams.sh` writes `webui-sha`. The Dockerfile reads that line from `VERSION`.
- Model lists: `scripts/patch-vendor-models.py` runs inside the image build, reading `/opt/hermes` and writing `/app/hermes-webui`.
- Vault: removed in 0.15.0. Do not install it, do not re-apply patch #42, do not add `vault-base`.

## Command cheat sheet

```bash
./scripts/read-version.sh
cat VERSION
./scripts/latest-hermes-tag.sh

./scripts/bump-hermes.sh v0.23.0        # hermes minor + Dockerfile HERMES_IMAGE
./scripts/bump-patch.sh                 # z+1 only; preserves webui pins
./scripts/set-version.sh 0.16.1 [tag]

. scripts/version-lib.sh && read_version_file .
pin_webui_base "v0.52.200"
./scripts/sync-upstreams.sh             # writes webui-sha; does not vendor
./scripts/smoke.sh
```

Detect other upstreams:

```bash
gh api repos/nesquena/hermes-webui/tags --jq '.[].name' | head -20
gh api repos/NousResearch/hermes-agent/releases --jq '.[:5]|.[]|{tag:.tag_name,name:.name}'
```

Skip experimental WebUI tags (`exp-*`) unless the user explicitly wants them.

## Routine upstream upgrade (keep this repo current)

The routine lane: **detect → validate the image tag → compatibility check → bump → doc
sweep → static checks → PR for human review → after merge, tag/release → deploy**.
Steps 1-7 are safe to run autonomously inside an approved "keep this repo up to date"
outcome. Steps 8-9 are maintainer actions: never merge, tag, publish an image, or deploy
on your own initiative.

### 1. Detect

```bash
./scripts/latest-hermes-tag.sh          # prints vX.Y.Z, or exits non-zero — it never guesses
./scripts/read-version.sh              # hermes_base / webui_base as key=value
```

Compare the printed tag with `VERSION` line `hermes-base`. Same → nothing to do.

**Tag scheme changed upstream (2026-11-05).** Image tags were CalVer (`v2026.9.24`) through
2026-11-04 and are semver (`v0.23.0`) since. The two are *not* comparable as version tuples:
`v2026.9.24` sorts above `v0.23.0`. `latest-hermes-tag.sh` therefore:

1. asks GitHub `releases/latest` for the current release tag,
2. validates that a Docker Hub image actually exists for it (`tag_status: active`),
3. falls back to a Docker Hub tag scan (both schemes) that ranks **semver above CalVer**
   and, within a scheme, the higher version,
4. exits **1** with the reason on stderr when no tag can be validated, instead of printing
   a stale CalVer tag.

`check-upstream.yml` uses the same ranking when it decides "needs bump". A numeric
`sort -V`/tuple compare there would report "Up to date" forever after the scheme change.

### 2. Validate the image tag exists before pinning

```bash
curl -fsS "https://hub.docker.com/v2/repositories/nousresearch/hermes-agent/tags/<tag>"
gh release view <tag> -R NousResearch/hermes-agent
```

Do not pin a tag that exists only as a git tag. A base pin with no image fails at
`FROM ${HERMES_IMAGE}` for everyone.

### 3. Base-image compatibility check (no docker daemon needed)

Read the upstream repo at the tag — `gh api "repos/NousResearch/hermes-agent/contents/<path>?ref=<tag>"`
— and record `assumption | still true | evidence` for:

| Assumption this image makes | Where |
|---|---|
| `ENTRYPOINT` is `/opt/hermes/docker/entrypoint-dispatch.sh` and `main-wrapper.sh` still routes args | `Dockerfile` CMD, `railway.toml` |
| `/opt/hermes/.venv` exists and is writable/owned as we chown it | `docker/s6-rc.d/*/run`, Dockerfile `uv pip` |
| **`uv` is resolvable at build time** — it left PATH in v0.23.0 and now comes from PM (`pm.uv_launcher("uv")`, `on_path = False`) | Dockerfile `uv pip install` block |
| `/opt/hermes/bin/hermes`, `plugins/`, `skills/`, `optional-skills/` ship in the image | `control_plane/s6_ops.py`, `cont-init.d/03-all-in-one-setup` |
| Node version baked at `/usr/local/bin/node` (`HERMES_NODE`) | README § Railway shells, Dockerfile ENV |
| `pyproject.toml [project.optional-dependencies] web` pins (fastapi/uvicorn/starlette) | Dockerfile `uv pip` block, `requirements-control-plane.txt` |
| `docker/patches/` table is still empty (retired patch still absorbed upstream) | `docker/patches/apply-agent-patches.sh` |
| The `webui-sha` archive fetch URL still resolves | Dockerfile webui RUN |
| `scripts/patch-vendor-models.py` still parses upstream catalogs | Dockerfile webui RUN |

Prove the model-list rewrite without docker (it is the step that fails a bump most often —
upstream renamed `List[str]` to `list[str]` in v0.23.0 and the parser exited 1):

```bash
# fetch the new catalogs into a scratch agent root + unpack the pinned WebUI
HERMES_AGENT_ROOT=<scratch>/agent HERMES_WEBUI_ROOT=<scratch>/webui \
  python3 scripts/patch-vendor-models.py     # must exit 0 and report model counts
# run twice: the second run must say "already up to date" (idempotent)
python3 -m py_compile <scratch>/webui/api/config.py
```

If a parser assumption broke, fix `scripts/patch-vendor-models.py` (tolerate old and new
shapes), never the generated file. Empty OpenRouter/Codex parses are fatal by design.

### 4. Bump

```bash
git fetch origin --prune
git checkout main && git merge --ff-only origin/main    # not FF? stop and report
git switch -c chore/bump-hermes-<tag>
./scripts/bump-hermes.sh <tag>
```

Expect: package `y+1`, `z→0`; `hermes-base=<tag>`; Dockerfile `ARG HERMES_IMAGE`; and
`webui-base`/`webui-sha` byte-identical. If the script mangles a line, fix
`scripts/version-lib.sh`, not the output.

### 5. Doc sweep

```bash
grep -rn "<previous-tag>" --exclude-dir=.git .    # every live pin/example
```

README (base-image table, `HERMES_IMAGE` row, build example, `VERSION` example, bump-rule
example, maintainer scripts, release-flow examples, release-notes example), this skill's
version block + cheat sheet, `docker/patches/README.md`'s "empty as of" claim (re-check
before relabelling), and Dockerfile comments that assert a base-image fact. Leave genuine
history and published release-note text alone.

### 6. Static checks

```bash
bash -n <every modified shell script>
bash docker/patches/test-apply-agent-patches.sh
python3 -m pytest tests/
./scripts/smoke.sh          # only with a reachable docker daemon; otherwise say the gap
```

No docker here? Record the gap explicitly and rely on the PR's `ci.yml` `vendor syntax` +
`smoke` jobs. Do not claim smoke passed.

### 7. PR for human review

Conventional commit (`chore(release): X.Y.Z on hermes <tag>`), push the branch, `gh pr
create --base main` with: pin table, why this tag, the compatibility table from step 3,
verification actually run **plus gaps**, and rollback. Required checks: `vendor syntax` +
`smoke`. The maintainer merges.

### 8. After merge — maintainer only

Tag must equal `VERSION` line 1: `git tag vX.Y.Z && git push origin vX.Y.Z` → `release.yml`
preflight → amd64 + arm64 → manifest → GHCR `:vX.Y.Z` + `:latest` → stub GitHub Release →
`gh release edit` with curated notes.

### 9. Deploy — human-gated

Publishing an image is not deploying. Moving a Railway/consumer workload onto the new tag
is a human decision; an agent may prepare the pin and the rollback, not perform the deploy.

### Rollback

The bump is one reversible commit pair (`VERSION`, `Dockerfile`): `git revert` the merge
commit, or re-pin the previous base with `./scripts/set-version.sh <old-package> <old-tag>`
and bump a patch. Then republish. Never delete or force-push a published tag; ship the
revert as a new version.

## Full cycle checklist

```
### 0. Orient
- [ ] Read VERSION + origin/main VERSION
- [ ] Read this skill (`.agents/skills/hermes-all-in-one-release/SKILL.md`)
- [ ] git fetch origin --tags --prune
- [ ] Clean branch from main (or adopt existing chore/bump-*)

### 1. Detect upstreams
- [ ] hermes-agent vs hermes-base
- [ ] stable hermes-webui vs webui-base (ignore exp-*)
- [ ] Decide minor vs patch. Vault is not a pin.

### 2. Branch + pins
- [ ] Branch: chore/bump-hermes-<tag> or chore/release-vX.Y.Z
- [ ] If check-upstream PR exists: checkout it
- [ ] bump-hermes / bump-patch / set-version + pin_webui_base + sync-upstreams.sh as needed
- [ ] Dockerfile HERMES_IMAGE matches hermes-base when hermes moved
- [ ] webui-sha is the commit of webui-base. Dockerfile reads it from VERSION

### 3. Glue
- [ ] No vendor/ directory. Do not subtree-pull or archive-replace
- [ ] README VERSION example matches pins
- [ ] Agent patch table still empty, or a new row has a file under docker/patches/agent/

### 4. Verify
- [ ] ./scripts/smoke.sh PASS
- [ ] `bash docker/patches/test-apply-agent-patches.sh` PASS
- [ ] Smoke log shows the WebUI fetch of webui-sha and WebUI version v<package>

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
| hermes-base | … (Agent v…) | **…** |
| webui-base / webui-sha | … | … |

### Changes in this PR
- Dockerfile / VERSION pins
- Layer fixes. No vendor tree. No Vault.
- README VERSION example

### Other upstreams checked
- hermes-webui: …
- hermes-vault: not installed. Do not re-add.

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

1. Read `VERSION`. Classify Hermes vs WebUI vs layer-only. Vault is gone.
2. Detect latest Hermes and stable WebUI tags. Report moves vs holds.
3. `bump-patch.sh` does not write `webui-base` or `webui-sha`. Do not claim it does.
4. Do not vendor. A WebUI pin move is `pin_webui_base` plus `./scripts/sync-upstreams.sh`.
5. Model-list rewrite runs in the image build. Do not commit a patched WebUI tree.
6. README VERSION example matches.
7. `./scripts/smoke.sh` before merge/tag confidence.
8. PR with full body; explicit path staging.
9. Merge only if asked; then pull main, tag, push tag.
10. Watch `release.yml` green.
11. **`gh release edit`** full notes. Never leave the stub.
12. Summarize: pins, PR URL, tag, image, release URL.

**Commit messages:** `chore(release): 0.15.0 on hermes v…` · `chore(sync): pin webui-sha …` · `fix(scope): …` + patch bump.

## Automation vs ad-hoc

| What | How |
|------|-----|
| New Hermes on Docker Hub | `check-upstream.yml` → pin-only PR, comparing tags scheme-aware (semver outranks retired CalVer). Do not vendor. Rewrite the PR body. |
| Newer stable WebUI tag | `sync-upstreams.yml` writes `webui-base` + `webui-sha`. Does not vendor. |
| PR validation | `ci.yml`: **vendor syntax** + **smoke** |
| Publish image + stub Release | Tag `vX.Y.Z` → `release.yml` |
| Curated notes | **Manual** `gh release edit` |

Bot PRs may stall (`action_required`). Prefer human-user push.

## Troubleshooting

| Issue | Action |
|-------|--------|
| `bump-hermes` no-op | Already on that hermes-base |
| WebUI pin moved but image unchanged | `webui-sha` missing or Dockerfile not reading `VERSION`. `./scripts/sync-upstreams.sh`, then smoke. |
| Someone asks to re-apply vault #42 | Vault is not installed. Do not. |
| Smoke apt fail (macOS) | `docker build --network=host` then `SMOKE_SKIP_BUILD=1 ./scripts/smoke.sh` |
| Release preflight fail | Tag must match VERSION line 1 |
| Notes still stub | `gh release edit` after green |
| Draft release stuck unpublished | Never pre-create `--draft`; edit after workflow create |
| Local tag collision | `git tag -d vX.Y.Z` if unrelated SHA; retag |
| `latest-hermes-tag.sh` exits 1 | Neither GitHub `releases/latest` nor the Docker Hub scan produced a validated tag (rate limit, outage, or a release with no image). Read the stderr reasons; pin an explicitly verified tag or re-run. Do not fall back to the old CalVer filter. |
| Build fails: "OpenRouter/Codex model list is empty" | Upstream renamed or retyped the catalog table (v0.23.0 changed `List[str]` → `list[str]` in `codex_models.py`). Fix `scripts/patch-vendor-models.py` to accept both shapes; never edit the generated WebUI file. |
| Build fails: `uv: not found` | v0.23.0 dropped uv from PATH — it is an internal PM package now. Resolve it with `pm.uv_launcher("uv")` (after `pm.ensure("uv", explicit=True)`); do not re-add a `COPY --from=ghcr.io/astral-sh/uv` or pip install. |
| `check-upstream` says "Up to date" after a scheme change | The compare must rank semver above retired CalVer tags; a numeric tuple/`sort -V` compare ranks `v2026.9.24` above `v0.23.0`. |
| Skill not found | Open `.agents/skills/hermes-all-in-one-release/SKILL.md` in-repo (not global) |

## More detail

- [README.md § Releases & versioning](../../../README.md#releases--versioning)
- [examples.md](examples.md)
