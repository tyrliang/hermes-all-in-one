---
name: hermes-all-in-one-release
description: >-
  Release and version hermes-all-in-one: bump package semver (x.y.z), pin
  hermes-base/agent-base/webui-base, run smoke tests, and publish GHCR via
  git tags. Use when the user asks to release, bump version, publish an
  image, adopt a new Hermes Agent base, run the release pipeline, or tag
  v0.x.z. Most releases need zero commands — see "Default path" below.
---

# hermes-all-in-one Release

## Default path: no commands needed

`upstream-refresh.yml` runs daily, detects new Hermes Agent (Docker Hub image
+ git tag) and hermes-webui releases, and opens **one** PR
(`automation/upstream-refresh`) with the vendor sync, `VERSION`, and
Dockerfile pin already done. `ci.yml` (`vendor syntax` + `smoke`) is a
**required check on `main`** — the PR can't merge until both are green.

**The whole job is: review the PR diff, confirm CI is green, merge.**
`auto-tag-release.yml` then tags the new version and pushes, which triggers
`release.yml` (build + GHCR + GitHub Release). Nothing else to run.

Reach for the scripts below only for: a layer-only patch (no upstream
change), or forcing a Hermes bump ahead of the daily cron.

## Version model

Four fields in root `VERSION`:

```text
0.6.0
hermes-base=v2026.7.1
agent-base=v2026.7.1
webui-base=v0.51.919
```

| Line | Field | Meaning | Who/what bumps |
|------|-------|---------|-----------------|
| 1 | Package semver | Git tag `v0.6.0`, GHCR tag | Auto (Hermes bump) or `bump-patch.sh` |
| 2 | `hermes-base` | `nousresearch/hermes-agent` Docker tag baked into the Dockerfile | `upstream-refresh.yml` / `bump-hermes.sh` |
| 3 | `agent-base` | `hermes-agent` git tag for the `vendor/hermes-agent` subtree (model lists only — not shipped) | Same as `hermes-base`, always in lockstep |
| 4 | `webui-base` | `hermes-webui` git tag for the `vendor/hermes-webui` subtree (shipped in the image) | `upstream-refresh.yml`, independent |

`hermes-base` and `agent-base` are the same upstream release consumed two
ways and must never drift apart — `bump-hermes.sh` and `upstream-refresh.yml`
always set both together.

**Bump rules**

| Change | Bump | Example |
|--------|------|---------|
| New Hermes Agent base | **y** + 1, **z** → 0 | `0.5.0` → `0.6.0` |
| webui-only vendor sync | none | `webui-base` moves, semver unchanged |
| All-in-one-only fix (same Hermes base) | **z** + 1 | `0.6.0` → `0.6.1` |
| Breaking packaging | **x** + 1 (manual, rare) | `set-version.sh` |

A `VERSION` change landing on `main` is what publishes — `auto-tag-release.yml`
tags it and pushes, which triggers `release.yml`. Pushing to `main` without a
`VERSION` change does **not** publish.

## Automation vs ad-hoc

| What | How |
|------|-----|
| Detect new Hermes (image+tag) and webui, open PR with everything wired up | Daily `upstream-refresh.yml` |
| PR validation, required before merge | `ci.yml` (`vendor syntax` + `smoke`) |
| Tag + push on `VERSION` merge | `auto-tag-release.yml` (automatic, no command) |
| Publish image + GitHub Release | `release.yml`, triggered by the tag push above |

**Default maintainer path:** review + merge the daily `upstream-refresh` PR. That's it — no scripts, no tagging.

## Command cheat sheet

Only needed for ad-hoc / manual paths:

```bash
# Inspect current versions
./scripts/read-version.sh
cat VERSION

# Latest Hermes tag on Docker Hub
./scripts/latest-hermes-tag.sh

# Adopt new Hermes base now (y+1, z=0, pins Dockerfile + agent-base)
./scripts/bump-hermes.sh v2026.7.1

# Layer-only release (z+1, all bases unchanged)
./scripts/bump-patch.sh

# Explicit set (rare)
./scripts/set-version.sh 0.4.1 v2026.6.5

# Validate before pushing (build + runtime smoke)
./scripts/smoke.sh
```

**Smoke shortcuts**

```bash
SMOKE_SKIP_BUILD=1 ./scripts/smoke.sh   # reuse local image
docker build --network=host -t hermes-control-plane-smoke:local .  # if apt fails in BuildKit on macOS
```

## Ad-hoc workflows

Copy checklist and track progress.

### A. Layer-only patch (most common ad-hoc)

Use when you changed control-plane, docker glue, or vendored WebUI — **same** bases.

```
- [ ] ./scripts/bump-patch.sh
- [ ] ./scripts/smoke.sh
- [ ] git commit -am "fix: …"
- [ ] git push origin main    # auto-tag-release.yml tags + releases automatically
```

### B. Hermes bump right now (skip waiting for the daily PR)

```
- [ ] ./scripts/latest-hermes-tag.sh          # confirm target tag exists on Docker Hub
- [ ] ./scripts/bump-hermes.sh v2026.7.1
- [ ] ./scripts/smoke.sh
- [ ] git add VERSION Dockerfile
- [ ] git commit -m "chore(release): adopt Hermes Agent v2026.7.1"
- [ ] open a PR (required checks gate merge) or push straight to main
```

Optional: trigger the check early via GitHub Actions → **Upstream Refresh** → Run workflow, instead of doing this by hand.

### C. Finish the daily upstream PR (default path — no scripts)

When `upstream-refresh.yml` opened `automation/upstream-refresh`:

```
- [ ] Review PR diff (VERSION, Dockerfile, vendor/)
- [ ] Confirm CI (vendor syntax + smoke) is green — required, can't merge otherwise
- [ ] Merge PR to main
```

Nothing after merge — `auto-tag-release.yml` tags, `release.yml` publishes.

### D. Release without version bump (re-publish same tag)

Avoid unless fixing a failed release. Prefer `bump-patch.sh` instead. Re-tagging requires deleting the remote tag/release first (auto-tag-release.yml is idempotent and won't re-tag an existing version).

## Agent instructions

When the user asks to release:

1. Check if an `automation/upstream-refresh` PR is already open and green — if so, that's the whole answer: merge it.
2. Otherwise read `VERSION` and confirm intent: **Hermes bump** vs **layer patch**.
3. Run the matching bump script; do not hand-edit `VERSION` unless `set-version.sh` is needed.
4. Run `./scripts/smoke.sh` before pushing. Fix failures before proceeding.
5. Push/merge to `main`. Do **not** manually tag or run `gh release create` — `auto-tag-release.yml` and `release.yml` handle both automatically once `VERSION` changes on `main`.

**Do not** push to GHCR manually, and do not `git tag` by hand for a normal bump — the automation does it and skips if the tag already exists.

**Commit messages**

- Hermes bump: `chore(release): adopt Hermes Agent v2026.7.1`
- Layer patch: `fix(scope): …` plus version bump in same or follow-up commit

## Workflows reference

| File | Trigger | Role |
|------|---------|------|
| `.github/workflows/ci.yml` | PR / branch push | `vendor syntax` + smoke — **required on `main`** |
| `.github/workflows/upstream-refresh.yml` | Daily 04:00 UTC | Opens one PR: Hermes (image+vendor+semver) and/or webui vendor sync |
| `.github/workflows/auto-tag-release.yml` | Push to `main` touching `VERSION` | Tags `vX.Y.Z`, pushes → triggers release.yml |
| `.github/workflows/release.yml` | Tag `v*.*.*` | Build, GHCR, GitHub Release (with base-image table + compare link) |

Both automation workflows push as `SYNC_PAT` (a human PAT), not the default `GITHUB_TOKEN` — GitHub gates every `github-actions[bot]`-authored PR run behind manual approval, and `GITHUB_TOKEN` pushes never trigger other workflows. Without `SYNC_PAT`, the refresh PR still opens (safety guards still run inline) but CI won't auto-run and merges won't auto-tag.

## Troubleshooting

| Issue | Action |
|-------|--------|
| `bump-hermes` no-op | Already on that `hermes-base` — use `bump-patch` for layer changes |
| Smoke build apt fails (macOS) | `docker build --network=host …` then `SMOKE_SKIP_BUILD=1 ./scripts/smoke.sh` |
| Release workflow fails tag check | Tag must match `VERSION` line 1 exactly (`v0.6.0` ↔ `0.6.0`) |
| `upstream-refresh` PR stuck with no CI checks | `SYNC_PAT` missing/expired — CI on bot-authored PRs needs it (see Workflows reference) |
| `agent-base` and `hermes-base` disagree | Should never happen via automation (they're pinned together); if hand-edited, re-run `bump-hermes.sh <tag>` to realign |

## More detail

See [README.md § Releases & versioning](../../README.md#releases--versioning) and [examples.md](examples.md).
