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
0.15.0
hermes-base=v2026.9.24
webui-base=v0.52.113
webui-sha=c67fd2dd270a1128c2754200406bca58e9d9a25a
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

./scripts/bump-hermes.sh v2026.9.24     # hermes minor + Dockerfile HERMES_IMAGE
./scripts/bump-patch.sh                 # z+1 only; preserves webui pins
./scripts/set-version.sh 0.15.1 [tag]

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
| New Hermes on Docker Hub | `check-upstream.yml` → pin-only PR. Do not vendor. Rewrite the PR body. |
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
| Skill not found | Open `.agents/skills/hermes-all-in-one-release/SKILL.md` in-repo (not global) |

## More detail

- [README.md § Releases & versioning](../../../README.md#releases--versioning)
- [examples.md](examples.md)
