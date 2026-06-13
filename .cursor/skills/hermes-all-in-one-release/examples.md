# Release examples

## Example 1: Tailscale fix on same Hermes base

Current `VERSION`:

```text
0.3.9
hermes-base=v2026.6.5
```

```bash
# after fixing docker/cont-init.d/04-tailscale-env
./scripts/bump-patch.sh          # → 0.3.10
./scripts/smoke.sh
git add -A
git commit -m "fix(tailscale): correct proxy NO_PROXY for AWS endpoints"
git push origin main
git tag v0.3.10
git push origin v0.3.10
```

Published: `ghcr.io/<owner>/hermes-all-in-one:v0.3.10` on Hermes `v2026.6.5`.

---

## Example 2: Merge auto upstream PR

GitHub opened PR **chore(release): adopt Hermes v2026.7.1** with:

```text
0.4.0
hermes-base=v2026.7.1
```

After CI green and merge:

```bash
git checkout main && git pull
./scripts/smoke.sh               # optional local sanity check
git tag v0.4.0
git push origin v0.4.0
```

---

## Example 3: Manual Hermes bump (don't wait for cron)

```bash
./scripts/latest-hermes-tag.sh
# v2026.7.1

./scripts/bump-hermes.sh v2026.7.1
./scripts/sync-upstreams.sh      # optional; needs clean tree
./scripts/smoke.sh

git add VERSION Dockerfile
git commit -m "chore(release): 0.4.0 on hermes v2026.7.1"
git push origin main
git tag v0.4.0
git push origin v0.4.0
```

---

## Example 4: Check versions in CI locally

```bash
./scripts/read-version.sh
# semver=0.3.9
# hermes_base=v2026.6.5
```

Use before tagging to avoid release.yml tag mismatch failures.
