#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_TAG="${SMOKE_IMAGE_TAG:-hermes-control-plane-smoke:local}"
CONTAINER_NAME="hermes-control-plane-smoke"
HOST_PORT="${SMOKE_PORT:-18787}"
CONTAINER_PORT="${SMOKE_CONTAINER_PORT:-18999}"
DATA_DIR="${SMOKE_DATA_DIR:-${ROOT_DIR}/.tmp-smoke-data}"
WEBUI_PASSWORD="${SMOKE_WEBUI_PASSWORD:-smoke-webui-password}"
ADMIN_PASSWORD="${SMOKE_ADMIN_PASSWORD:-smoke-admin-password}"
COOKIE_JAR="${DATA_DIR}/admin-cookies.txt"
BASE_URL="http://127.0.0.1:${HOST_PORT}"

cleanup() {
  docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

require() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "[smoke] missing required command: $1" >&2
    exit 1
  }
}

wait_for_health() {
  local url="$1"
  for ((i=1; i<=60; i++)); do
    if curl --silent --show-error --fail "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "[smoke] timed out waiting for health: ${url}" >&2
  return 1
}

assert_eq() {
  local actual="$1"
  local expected="$2"
  local message="$3"
  if [[ "$actual" != "$expected" ]]; then
    echo "[smoke] assertion failed: ${message}" >&2
    echo "  expected: ${expected}" >&2
    echo "  actual:   ${actual}" >&2
    exit 1
  fi
}

assert_http() {
  local url="$1"
  local expected="$2"
  local message="$3"
  local actual
  actual="$(curl --silent --output /dev/null --write-out '%{http_code}' "$url")"
  if [[ "$actual" != "$expected" ]]; then
    echo "[smoke] assertion failed: ${message}" >&2
    echo "  expected HTTP ${expected}, got ${actual} for ${url}" >&2
    exit 1
  fi
}

smoke_run_container() {
  docker run -d \
    --name "${CONTAINER_NAME}" \
    -p "${HOST_PORT}:${CONTAINER_PORT}" \
    -e PORT="${CONTAINER_PORT}" \
    -e HERMES_WEBUI_PASSWORD="${WEBUI_PASSWORD}" \
    -e HERMES_ADMIN_PASSWORD="${ADMIN_PASSWORD}" \
    -e HOME=/opt/data \
    -e HERMES_DATA_DIR=/opt/data \
    -e HERMES_HOME=/opt/data/.hermes \
    -e HERMES_CONFIG_PATH=/opt/data/.hermes/config.yaml \
    -e HERMES_WEBUI_STATE_DIR=/opt/data/webui \
    -e HERMES_WORKSPACE_DIR=/opt/data/workspace \
    -e HERMES_WEBUI_AGENT_DIR=/opt/hermes \
    -e CONTROL_PLANE_RUNTIME=s6 \
    -v "${DATA_DIR}:/opt/data" \
    "${IMAGE_TAG}" >/dev/null
}

require docker
require curl
require python3

rm -rf "${DATA_DIR}"
mkdir -p "${DATA_DIR}"
cleanup

cd "${ROOT_DIR}"

# shellcheck source=scripts/version-lib.sh
. "${ROOT_DIR}/scripts/version-lib.sh"
read_version_file "$ROOT_DIR" || true

if [[ "${SMOKE_SKIP_BUILD:-0}" != "1" ]]; then
  echo "[smoke] building image ${IMAGE_TAG}"
  build_args=()
  if [[ -n "${PACKAGE_VERSION:-}" ]]; then
    build_args+=(--build-arg "HERMES_WEBUI_VERSION=v${PACKAGE_VERSION}")
  fi
  if [[ -n "${HERMES_BASE:-}" ]]; then
    build_args+=(--build-arg "HERMES_IMAGE=nousresearch/hermes-agent:${HERMES_BASE}")
  fi
  docker build "${build_args[@]}" -t "${IMAGE_TAG}" .
else
  echo "[smoke] skipping build (SMOKE_SKIP_BUILD=1)"
fi

echo "[smoke] starting container with PORT=${CONTAINER_PORT}"
smoke_run_container

wait_for_health "${BASE_URL}/health"

echo "[smoke] checking /health payload"
health_json="$(curl --silent --show-error --fail "${BASE_URL}/health")"
python3 - <<'PY' "$health_json"
import json, sys
payload = json.loads(sys.argv[1])
assert payload.get("service") == "hermes-control-plane", payload
assert payload.get("status") == "ok", payload
webui = payload.get("webui") or {}
assert webui.get("healthy") is True, webui
assert webui.get("running") is True, webui
assert webui.get("supervisor") == "s6", webui
assert webui.get("service") == "/run/service/hermes-webui", webui
gateway = payload.get("gateway") or {}
assert "running" in gateway and "healthy" in gateway, gateway
print("[smoke] /health payload OK")
PY

echo "[smoke] checking public routing"
root_status="$(curl --silent --output /dev/null --write-out '%{http_code}' "${BASE_URL}/")"
admin_status="$(curl --silent --output /dev/null --write-out '%{http_code}' "${BASE_URL}/admin")"
login_status="$(curl --silent --output /dev/null --write-out '%{http_code}' "${BASE_URL}/admin/login")"
case "$root_status" in
  200|302|303) ;;
  *)
    echo "[smoke] expected / to serve or redirect to WebUI auth, got ${root_status}" >&2
    exit 1
    ;;
esac
case "$admin_status" in
  302|303) ;;
  *)
    echo "[smoke] expected /admin to require auth, got ${admin_status}" >&2
    exit 1
    ;;
esac
assert_eq "$login_status" "200" "/admin/login should render"
assert_http "${BASE_URL}/login" "200" "WebUI login page should proxy through control plane"

echo "[smoke] checking admin auth gate"
unauth_status="$(curl --silent --output /dev/null --write-out '%{http_code}' "${BASE_URL}/admin/api/status")"
case "$unauth_status" in
  302|303|401) ;;
  *)
    echo "[smoke] expected unauthenticated /admin/api/status to be rejected, got ${unauth_status}" >&2
    exit 1
    ;;
esac

echo "[smoke] checking volume bootstrap and baked tooling"
docker exec "${CONTAINER_NAME}" /bin/sh -lc '
  set -eu
  test -d /opt/data/.hermes
  test -d /opt/data/webui
  test -d /opt/data/workspace
  test -d /opt/hermes
  test -s /opt/data/.hermes/pairing/telegram-approved.json
  test -s /opt/data/.hermes/pairing/telegram-pending.json
  test -x /usr/local/bin/micro
  test -x /usr/local/bin/node
  command -v zsh >/dev/null
  curl --silent --show-error --fail http://127.0.0.1:8788/health >/dev/null
'
echo "[smoke] bootstrap dirs, agent mount, shell tools, internal WebUI OK"

if [[ -n "${PACKAGE_VERSION:-}" && "${SMOKE_SKIP_BUILD:-0}" != "1" ]]; then
  expected_webui_version="v${PACKAGE_VERSION}"
  actual_webui_version="$(docker exec "${CONTAINER_NAME}" /opt/hermes/.venv/bin/python -c \
    "import importlib.util; spec=importlib.util.spec_from_file_location('v','/app/vendor/hermes-webui/api/_version.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print(m.__version__)")"
  assert_eq "$actual_webui_version" "$expected_webui_version" "WebUI version should match VERSION file"
  echo "[smoke] WebUI version ${actual_webui_version} OK"
fi

echo "[smoke] logging into /admin"
curl --silent --show-error --fail \
  -c "${COOKIE_JAR}" \
  -d "password=${ADMIN_PASSWORD}" \
  -X POST "${BASE_URL}/admin/login" \
  -o /dev/null >/dev/null

status_json="$(curl --silent --show-error --fail -b "${COOKIE_JAR}" "${BASE_URL}/admin/api/status")"
python3 - <<'PY' "$status_json"
import json, sys
payload = json.loads(sys.argv[1])
paths = payload["paths"]
assert paths["config_path"] == "/opt/data/.hermes/config.yaml"
assert paths["hermes_home"] == "/opt/data/.hermes"
assert paths["webui_state_dir"] == "/opt/data/webui"
assert paths["workspace_dir"] == "/opt/data/workspace"
assert paths["env_path"] == "/opt/data/.hermes/.env"
webui = payload["webui"]
assert webui["supervisor"] == "s6", webui
assert webui["healthy"] is True, webui
gateway = payload["gateway"]
assert gateway["supervisor"] == "s6", gateway
assert "autostart_eligible" in gateway, gateway
assert isinstance(payload.get("provider_catalog"), list) and payload["provider_catalog"], payload
print("[smoke] admin status paths and supervisors OK")
PY

echo "[smoke] checking read-only admin APIs"
channels_json="$(curl --silent --show-error --fail -b "${COOKIE_JAR}" "${BASE_URL}/admin/api/channels")"
pending_json="$(curl --silent --show-error --fail -b "${COOKIE_JAR}" "${BASE_URL}/admin/api/pairing/pending")"
approved_json="$(curl --silent --show-error --fail -b "${COOKIE_JAR}" "${BASE_URL}/admin/api/pairing/approved")"
python3 - <<'PY' "$channels_json" "$pending_json" "$approved_json"
import json, sys
channels, pending, approved = map(json.loads, sys.argv[1:])
assert channels.get("ok") is True, channels
assert "values" in channels, channels
assert pending.get("ok") is True, pending
assert isinstance(pending.get("pending"), list), pending
assert approved.get("ok") is True, approved
assert isinstance(approved.get("approved"), list), approved
print("[smoke] admin read-only APIs OK")
PY

echo "[smoke] exercising control-plane actions"
curl --silent --show-error --fail -b "${COOKIE_JAR}" -X POST "${BASE_URL}/admin/api/webui/restart" -o /dev/null >/dev/null
wait_for_health "${BASE_URL}/health"
curl --silent --show-error --fail -b "${COOKIE_JAR}" -X POST "${BASE_URL}/admin/api/gateway/restart" -o /dev/null >/dev/null
wait_for_health "${BASE_URL}/health"

signing_before="$(docker exec "${CONTAINER_NAME}" /bin/sh -lc 'test -f /opt/data/.admin_signing_key && sha256sum /opt/data/.admin_signing_key | awk "{print \$1}"')"
if [[ -z "$signing_before" ]]; then
  echo "[smoke] assertion failed: admin signing key should exist after login" >&2
  exit 1
fi

echo "[smoke] restarting container with same /opt/data volume"
docker rm -f "${CONTAINER_NAME}" >/dev/null

smoke_run_container

wait_for_health "${BASE_URL}/health"
signing_after="$(docker exec "${CONTAINER_NAME}" /bin/sh -lc 'test -f /opt/data/.admin_signing_key && sha256sum /opt/data/.admin_signing_key | awk "{print \$1}"')"
assert_eq "$signing_after" "$signing_before" "Admin signing key should persist across restart"

echo "[smoke] PASS"
