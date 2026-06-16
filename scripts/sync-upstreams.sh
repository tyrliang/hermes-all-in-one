#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

# shellcheck source=scripts/version-lib.sh
. "${ROOT_DIR}/scripts/version-lib.sh"
read_version_file "$ROOT_DIR" || true

AGENT_REMOTE_NAME="hermes-agent-upstream"
AGENT_REMOTE_URL="https://github.com/NousResearch/hermes-agent.git"
AGENT_REMOTE_REF="main"
AGENT_PREFIX="vendor/hermes-agent"

WEBUI_REMOTE_NAME="hermes-webui-upstream"
WEBUI_REMOTE_URL="https://github.com/nesquena/hermes-webui.git"
WEBUI_REMOTE_REF="master"
WEBUI_PREFIX="vendor/hermes-webui"

run() {
  echo "+ $*"
  "$@"
}

fail() {
  echo "[sync] $*" >&2
  exit 1
}

ensure_clean_tree() {
  git diff --quiet || fail "working tree has unstaged changes"
  git diff --cached --quiet || fail "index has staged changes"
  if [[ -n "$(git ls-files --others --exclude-standard)" ]]; then
    fail "working tree has untracked files"
  fi
}

ensure_remote() {
  local name="$1"
  local url="$2"
  local current
  current="$(git remote get-url "$name" 2>/dev/null || true)"
  if [[ -z "$current" ]]; then
    run git remote add "$name" "$url"
    return
  fi
  if [[ "$current" != "$url" ]]; then
    fail "remote $name points to $current, expected $url"
  fi
}

ensure_clean_tree
ensure_remote "$AGENT_REMOTE_NAME" "$AGENT_REMOTE_URL"
ensure_remote "$WEBUI_REMOTE_NAME" "$WEBUI_REMOTE_URL"

# hermes-webui is pinned to webui-base in VERSION (a tag or commit sha) so the
# subtree merge is deterministic and reviewable; bumping the pin is a deliberate
# act, not a nightly drift. Falls back to the branch head when unset.
WEBUI_PULL_REF="${WEBUI_BASE:-$WEBUI_REMOTE_REF}"
echo "[sync] hermes-webui pull ref: ${WEBUI_PULL_REF} (pinned via webui-base=${WEBUI_BASE:-unset})"

run git fetch "$AGENT_REMOTE_NAME" "$AGENT_REMOTE_REF"
# Fetch the branch so the pinned ref's objects are present even when it is not
# the branch tip.
run git fetch "$WEBUI_REMOTE_NAME" "$WEBUI_REMOTE_REF"
run git subtree pull --prefix="$AGENT_PREFIX" "$AGENT_REMOTE_NAME" "$AGENT_REMOTE_REF" --squash
run git subtree pull --prefix="$WEBUI_PREFIX" "$WEBUI_REMOTE_NAME" "$WEBUI_PULL_REF" --squash

echo
echo "[sync] patching vendor model lists from hermes-agent..."
python3 "${ROOT_DIR}/scripts/patch-vendor-models.py"
if ! git diff --quiet vendor/hermes-webui/api/config.py; then
  git add vendor/hermes-webui/api/config.py
  git commit -m "chore(sync): patch webui model list from hermes-agent"
fi

# Guard: a botched subtree merge (unresolved conflict markers) or a bad model
# patch must never be handed off. Fail loudly so the operator/CI stops here.
# Match only the opening/closing markers (git always writes them with a
# trailing space + label). A bare '=======' is skipped — it legitimately
# appears as a section underline in some vendored files.
if git grep -nE '^(<<<<<<<|>>>>>>>) ' -- vendor/ >/dev/null 2>&1; then
  echo "[sync] conflict markers found in vendor/:" >&2
  git grep -nE '^(<<<<<<<|>>>>>>>) ' -- vendor/ >&2 || true
  fail "unresolved conflict markers in vendor/ after sync"
fi
run python3 -m compileall -q "$AGENT_PREFIX" "$WEBUI_PREFIX" \
  || fail "vendored python does not byte-compile after sync"

echo "[sync] upstream refresh complete"
echo "[sync] next steps:"
echo "  1. Review changes in vendor/ and root integration files"
echo "  2. Run ./scripts/smoke.sh"
echo "  3. If Hermes base changed: ./scripts/bump-hermes.sh <tag>  OR  ./scripts/bump-patch.sh for layer-only fixes"
echo "  4. Tag v\$(head -1 VERSION) and push to publish (see .github/workflows/release.yml)"
