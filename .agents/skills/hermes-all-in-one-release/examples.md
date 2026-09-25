# Release examples

Historical cycles below vendored trees and shipped Vault. That stopped in 0.15.0. Do not repeat it.

Current cycle: bump `hermes-base` and/or `webui-base`+`webui-sha`, smoke, PR, tag, `gh release edit`. No `vendor/`. No Vault.
## Example A: Hermes + webui (v0.10.0 / PR #53)

**Session:** `…/2026-08-17T16-07-45-415Z_01a0107a-*.jsonl`

**User**

1. “update hermes agent to the latest upstream, v0.20.2 (v2026.8.16); also check if webui has new release. bump up the version and prepare for a release”
2. “make sure to write a release note, with detail note that talks about the feat/fix delta between hermes-agent version diff, as well any other version diff”
3. “ok merge pr 53, then work on the publish steps as per the PR”

**Agent:** bump-hermes + pin/vendor webui; patch-vendor-models; detailed PR/release notes with intermediate agent tags; merge; tag `v0.10.0`; watch build; `gh release edit`.

---

## Example B: Hermes + vault (v0.11.0 / PR #58)

**Session:** `…/chore-upgrade/2026-08-27T21-41-56-610Z_01a0452c-*.jsonl`

**User**

1. “look for upstream updates to hermes agent, webui etc. update to the latest version, run tests, create PR and prepare for version bump”
2. “ok go ahead and merge, then tag and push the new tag, watch the CI until done”
3. “make sure to write a release note… confirm what's skill we need to invoke next time”

**Agent**

| Pin | Was | Now |
|-----|-----|-----|
| package | 0.10.1 | 0.11.0 |
| hermes/agent | v2026.8.16 | v2026.8.27 |
| vault | v0.21.0 | v0.25.0 |
| webui | v0.52.113 | held (exp-* only newer) |

1. Pre-replace diffs → vault #42 local delta.
2. Archive-replace agent + vault; **re-apply #42** (`b3c09890db` class).
3. `pin_vault_base` is not done by `bump-patch.sh` — pin then bump semver (or hand-edit VERSION).
4. Smoke + vault service_ids tests; full PR body; tag; **`gh release edit`**.

**Skill next time:** `.agents/skills/hermes-all-in-one-release/` (repo path; read `SKILL.md`).

---

## Example C: Tag + retro notes

**Session:** `…/2026-07-31T19-42-41-330Z_019fb9b3-*.jsonl`

**User:** “pr 47 was just merged. do the work as planned” → “write proper release notes on github for v0.7.x and v0.8.x … so in the future we know what was changed between releases”

**Agent:** tag matching VERSION; watch release.yml; `gh release edit` on current and historical tags.

---

## Example D: Layer-only patch

Same hermes and webui pins → `./scripts/bump-patch.sh` (z+1 only) → smoke → PR → merge → tag → notes focused on layer changes.

```bash
./scripts/bump-patch.sh
./scripts/smoke.sh
# … PR, merge …
git tag "v$(head -1 VERSION)" && git push origin "v$(head -1 VERSION)"
gh release edit "v$(head -1 VERSION)" --notes-file /tmp/notes.md
```

---

## Release notes quality bar

Insufficient (workflow default): 2-line hermes-base + image stub.

Required: pin before/after table, layer bullets, curated upstream highlights,
upgrade pull line, verification. See GitHub releases `v0.11.0` and `v0.12.0`.

---

## Next-time one-liner

> Read `.agents/skills/hermes-all-in-one-release/SKILL.md` — detect agent/webui/vault → bump + `pin_*` →
> vendor (archive if needed) → vault #42 + patch-vendor-models → smoke → PR with
> upstream delta → merge when told → tag → watch release.yml → **`gh release edit`**.
