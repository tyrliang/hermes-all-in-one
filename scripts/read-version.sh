#!/usr/bin/env bash
# Emit version fields for CI (append stdout to GITHUB_OUTPUT).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/version-lib.sh
. "${ROOT_DIR}/scripts/version-lib.sh"

read_version_file "$ROOT_DIR"

echo "semver=${PACKAGE_VERSION}"
echo "hermes_base=${HERMES_BASE}"
echo "agent_base=${AGENT_BASE:-}"
echo "webui_base=${WEBUI_BASE:-}"
