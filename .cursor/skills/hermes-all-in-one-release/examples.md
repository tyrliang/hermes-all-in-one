# Release examples

## Example 1: Tailscale fix on same Hermes base

Current `VERSION`:

```text
0.6.0
hermes-base=v2026.7.1
agent-base=v2026.7.1
webui-base=v0.51.919
```

```bash
# after fixing docker/cont-init.d/04-tailscale-env
./scripts/bump-patch.sh          # → 0.6.1
./scripts/smoke.sh
git add -A
git commit -m "fix(tailscale): correct proxy NO_PROXY for AWS endpoints"
git push origin main
```

That's the whole release. `auto-tag-release.yml` sees `VERSION` changed on
`main`, tags `v0.6.1`, and pushes — `release.yml` builds and publishes:
`ghcr.io/<owner>/hermes-all-in-one:v0.6.1` on Hermes `v2026.7.1`.

---

## Example 2: Merge the daily upstream-refresh PR (default path)

GitHub opened PR **chore(release): upstream refresh** with:

```text
0.7.0
hermes-base=v2026.8.2
agent-base=v2026.8.2
webui-base=v0.51.919
```

```
- [ ] Review the diff (VERSION, Dockerfile, vendor/hermes-agent)
- [ ] Confirm CI is green — vendor syntax + smoke are required checks
- [ ] Merge
```

Nothing else. `auto-tag-release.yml` tags `v0.7.0` and pushes; `release.yml`
builds, pushes to GHCR, and creates the GitHub Release with the
hermes-base/agent-base/webui-base table and a compare link — automatically.

---

## Example 3: Manual Hermes bump (don't wait for cron)

```bash
./scripts/latest-hermes-tag.sh
# v2026.7.1

./scripts/bump-hermes.sh v2026.7.1
./scripts/smoke.sh

git add VERSION Dockerfile
git commit -m "chore(release): adopt Hermes Agent v2026.7.1"
git push origin main
```

No manual tag — `auto-tag-release.yml` picks up the `VERSION` change and
tags/publishes on its own. If pushing straight to `main` is blocked by
branch protection, open a PR instead; merging it triggers the same thing.

---

## Example 4: Check versions in CI locally

```bash
./scripts/read-version.sh
# semver=0.6.0
# hermes_base=v2026.7.1
# agent_base=v2026.7.1
# webui_base=v0.51.919
```

Useful for confirming `agent-base` and `hermes-base` are in lockstep before
trusting `vendor/hermes-agent`'s model lists.

---

## Example 5: webui-only vendor sync (no package version bump)

`upstream-refresh.yml` can land a webui-only change:

```text
0.6.0                    # unchanged
hermes-base=v2026.7.1    # unchanged
agent-base=v2026.7.1     # unchanged
webui-base=v0.51.930     # bumped
```

Merging this PR does **not** trigger `auto-tag-release.yml` — the package
version (line 1) didn't change, so there's nothing new to tag. The webui
vendor update just ships in the next Hermes-triggered release, or force a
patch release yourself with `./scripts/bump-patch.sh` if you need it out now.
