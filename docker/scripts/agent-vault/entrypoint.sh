#!/bin/sh
# Opt-in Agent Vault wrapper: when AGENT_VAULT_* is set, route outbound HTTPS through
# the remote broker before handing off to the official s6 /init chain.
set -e

if [ -n "${AGENT_VAULT_TOKEN:-}" ] && [ -n "${AGENT_VAULT_ADDR:-}" ]; then
  exec agent-vault run -- \
    /app/docker/scripts/agent-vault/install-broker-ca.sh \
    /app/docker/scripts/agent-vault/seed-agent-vault-skills.sh \
    /init /opt/hermes/docker/main-wrapper.sh "$@"
fi

exec /init /opt/hermes/docker/main-wrapper.sh "$@"
