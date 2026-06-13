#!/command/with-contenv sh
# shellcheck shell=sh
# Mirror docker -e / ENV into /run/s6/container_environment so s6 longruns
# (control-plane, hermes-webui) see the same values on all hosts.

set -eu

# shellcheck source=/app/docker/scripts/import-docker-env.sh
. /app/docker/scripts/import-docker-env.sh

CONT_ENV="/run/s6/container_environment"
if [ ! -d "${CONT_ENV}" ]; then
  exit 0
fi

import_docker_env \
  PORT \
  HERMES_ADMIN_PASSWORD \
  HERMES_WEBUI_PASSWORD \
  HERMES_DATA_DIR \
  HERMES_HOME \
  HERMES_CONFIG_PATH \
  HERMES_WEBUI_STATE_DIR \
  HERMES_WORKSPACE_DIR \
  HERMES_WEBUI_AGENT_DIR \
  HERMES_GATEWAY_AUTOSTART \
  TAILSCALE_AUTH_KEY \
  TAILSCALE_OUTBOUND_PROXY \
  TAILSCALE_SSH \
  TAILSCALE_SSH_AUTHORIZED_KEYS

for var in \
  PORT \
  HERMES_ADMIN_PASSWORD \
  HERMES_WEBUI_PASSWORD \
  HERMES_DATA_DIR \
  HERMES_HOME \
  HERMES_CONFIG_PATH \
  HERMES_WEBUI_STATE_DIR \
  HERMES_WORKSPACE_DIR \
  HERMES_WEBUI_AGENT_DIR \
  HERMES_GATEWAY_AUTOSTART \
  TAILSCALE_AUTH_KEY \
  TAILSCALE_OUTBOUND_PROXY \
  TAILSCALE_SSH \
  TAILSCALE_SSH_AUTHORIZED_KEYS
do
  eval "val=\${${var}-}"
  if [ -n "${val}" ]; then
    printf '%s' "${val}" > "${CONT_ENV}/${var}"
  fi
done

echo "[all-in-one] synced container env for supervised services"
