---
name: hermes-all-in-one-release
description: >-
  Release and version hermes-all-in-one: bump package semver (x.y.z), pin
  hermes-base, run smoke tests, and publish GHCR via git tags. Use when the user
  asks to release, bump version, publish an image, adopt a new Hermes Agent
  base, run the release pipeline, or tag v0.x.z.
---

# hermes-all-in-one Release

## Version model

Two fields in root `VERSION`:

```text
0.3.9
hermes-base=v2026.6.5
```

| Part | Meaning | Who bumps |
|------|---------|-----------|
| Line 1 `x.y.z` | Package semver → git tag `v0.3.9`, GHCR tag | You |
| Line 2 `hermes-base` | Pinned `nousresearch/hermes-agent` tag | Hermes adoption |

**Bump rules**

| Change | Bump | Example |
|--------|------|---------|
| New Hermes Agent base | **y** + 1, **z** → 0 | `0.3.9` → `0.4.0` |
| All-in-one-only fix (same Hermes base) | **z** + 1 | `0.4.0` → `0.4.1` |
| Breaking packaging | **x** + 1 (manual, rare) | `set-version.sh` |

Pushing to `main` does **not** publish. Only `git push origin vX.Y.Z` triggers `.github/workflows/release.yml`.

## Automation vs ad-hoc

| What | How |
|------|-----|
| Detect new Hermes on Docker Hub | Daily `check-upstream.yml` → opens bump PR |
| Vendor subtree sync | Daily `sync-upstreams.yml` (optional manual) |
| PR validation | `ci.yml` runs `./scripts/smoke.sh` |
| Publish image + GitHub Release | You tag `vX.Y.Z` after merge |

**Default maintainer path:** merge the auto bump PR (or your feature PR), run smoke locally if needed, tag, push tag.

## Command cheat sheet

Run from repo root:

```bash
# Inspect current versions
./scripts/read-version.sh
cat VERSION

# Latest Hermes tag on Docker Hub
./scripts/latest-hermes-tag.sh

# Adopt new Hermes base (y+1, z=0, pin Dockerfile)
./scripts/bump-hermes.sh v2026.6.5

# Layer-only release (z+1, hermes-base unchanged)
./scripts/bump-patch.sh

# Explicit set (optional hermes pin updates Dockerfile)
./scripts/set-version.sh 0.4.1 v2026.6.5

# Validate before tag (build + runtime smoke)
./scripts/smoke.sh

# Optional: refresh vendor subtrees before smoke
./scripts/sync-upstreams.sh

# Publish (after merge to main)
git tag v0.4.0
git push origin v0.4.0
```

**Smoke shortcuts**

```bash
SMOKE_SKIP_BUILD=1 ./scripts/smoke.sh   # reuse local image
docker build --network=host -t hermes-control-plane-smoke:local .  # if apt fails in BuildKit on macOS
```

## Ad-hoc workflows

Copy checklist and track progress.

### A. Layer-only patch (most common ad-hoc)

Use when you changed control-plane, docker glue, or vendored WebUI — **same** `hermes-base`.

```
- [ ] ./scripts/bump-patch.sh
- [ ] ./scripts/smoke.sh
- [ ] git commit -am "fix: …"
- [ ] git push origin main
- [ ] git tag v$(head -1 VERSION)
- [ ] git push origin v$(head -1 VERSION)
```

### B. Hermes bump (manual, skip waiting for daily PR)

Use when you want a specific Hermes tag now.

```
- [ ] ./scripts/latest-hermes-tag.sh          # confirm target tag
- [ ] ./scripts/bump-hermes.sh v2026.7.1
- [ ] ./scripts/sync-upstreams.sh             # optional
- [ ] ./scripts/smoke.sh
- [ ] git add VERSION Dockerfile [vendor/ …]
- [ ] git commit -m "chore(release): 0.4.0 on hermes v2026.7.1"
- [ ] git push origin main
- [ ] git tag v0.4.0 && git push origin v0.4.0
```

### C. Finish daily upstream PR (preferred for Hermes bumps)

When `check-upstream.yml` opened `chore/bump-hermes-v…`:

```
- [ ] Review PR diff (VERSION, Dockerfile)
- [ ] Wait for CI smoke green
- [ ] Merge PR to main
- [ ] git pull origin main
- [ ] git tag v$(head -1 VERSION)
- [ ] git push origin v$(head -1 VERSION)
```

Optional: trigger check early via GitHub Actions → **Check Hermes upstream** → Run workflow.

### D. Release without version bump (re-publish same tag)

Avoid unless fixing a failed release. Prefer `bump-patch.sh` instead. Re-tagging requires deleting the remote tag/release first.

## Agent instructions

When the user asks to release:

1. Read `VERSION` and confirm intent: **Hermes bump** vs **layer patch**.
2. Run the matching bump script; do not hand-edit `VERSION` unless `set-version.sh` is needed.
3. Run `./scripts/smoke.sh` before tagging. Fix failures before proceeding.
4. Ensure git tag matches line 1 of `VERSION` (with `v` prefix).
5. Push tag to trigger `release.yml` (smoke → amd64/arm64 build → GHCR → GitHub Release).

**Do not** push to GHCR manually; tag push handles it.

**Commit messages**

- Hermes bump: `chore(release): 0.4.0 on hermes v2026.7.1`
- Layer patch: `fix(scope): …` plus version bump in same or follow-up commit

## Workflows reference

| File | Trigger | Role |
|------|---------|------|
| `.github/workflows/ci.yml` | PR / branch push | Smoke only |
| `.github/workflows/release.yml` | Tag `v*.*.*` | Build, GHCR, GitHub Release |
| `.github/workflows/check-upstream.yml` | Daily 04:00 UTC | Open Hermes bump PR |
| `.github/workflows/sync-upstreams.yml` | Daily 03:00 UTC | Vendor subtree sync |

## Troubleshooting

| Issue | Action |
|-------|--------|
| `bump-hermes` no-op | Already on that `hermes-base` — use `bump-patch` for layer changes |
| Smoke build apt fails (macOS) | `docker build --network=host …` then `SMOKE_SKIP_BUILD=1 ./scripts/smoke.sh` |
| Release workflow fails tag check | Tag must match `VERSION` line 1 exactly (`v0.3.9` ↔ `0.3.9`) |
| Want WebUI vendor refresh | `./scripts/sync-upstreams.sh` (requires clean git tree) |

## More detail

See [README.md § Releases & versioning](../../README.md#releases--versioning) and [examples.md](examples.md).
