#!/bin/sh
# Fetch Agent Vault Hermes skills into the data volume at container start.
# Hermes reads skills from ${HERMES_HOME:-/opt/data}/skills (not ~/.hermes in Docker).
# Upstream embeds: Infisical/agent-vault cmd/skill_cli.md, cmd/skill_http.md
# https://docs.agent-vault.dev/quickstart/hermes-agent
set -e

DEST_ROOT="${HERMES_HOME:-/opt/data}/skills"
SKILLS_REF="${AGENT_VAULT_SKILLS_REF:-main}"
BASE_URL="https://raw.githubusercontent.com/Infisical/agent-vault/${SKILLS_REF}/cmd"

mkdir -p "$DEST_ROOT"

fetch_skill() {
  name=$1
  upstream=$2
  dest_dir="$DEST_ROOT/$name"
  dest="$dest_dir/SKILL.md"
  tmp=$(mktemp "${TMPDIR:-/tmp}/hermes-av-skill.XXXXXX") || exit 1

  if ! curl -fsSL --noproxy '*' --connect-timeout 10 --max-time 120 \
    "${BASE_URL}/${upstream}" -o "$tmp"; then
    rm -f "$tmp"
    if [ -f "$dest" ]; then
      echo "hermes-agent-vault: warn: could not refresh skill $name (keeping existing)" >&2
    else
      echo "hermes-agent-vault: warn: could not fetch skill $name from ${BASE_URL}/${upstream}" >&2
    fi
    return 0
  fi

  if [ ! -s "$tmp" ]; then
    rm -f "$tmp"
    echo "hermes-agent-vault: warn: empty skill payload for $name" >&2
    return 0
  fi

  if [ ! -f "$dest" ] || ! cmp -s "$tmp" "$dest"; then
    mkdir -p "$dest_dir"
    cp "$tmp" "$dest"
    chmod 644 "$dest"
    chown hermes:hermes "$dest_dir" "$dest" 2>/dev/null || true
    echo "hermes-agent-vault: synced skill $name -> $dest (ref=${SKILLS_REF})" >&2
  fi
  rm -f "$tmp"
}

fetch_skill agent-vault-cli skill_cli.md
fetch_skill agent-vault-http skill_http.md

exec "$@"
