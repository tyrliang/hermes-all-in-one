#!/usr/bin/env bash
# Adopt a new Hermes Agent base: bump minor (y), reset patch (z), pin Dockerfile.
# Usage: scripts/bump-hermes.sh v2026.6.5
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

# shellcheck source=scripts/version-lib.sh
. "${ROOT_DIR}/scripts/version-lib.sh"

HERMES_TAG="${1:?Usage: scripts/bump-hermes.sh <hermes-tag> (e.g. v2026.6.5)}"
HERMES_TAG="${HERMES_TAG#v}"
HERMES_TAG="v${HERMES_TAG}"

read_version_file "$ROOT_DIR"

if [[ "${HERMES_BASE}" == "${HERMES_TAG}" ]]; then
  echo "[bump-hermes] already on ${HERMES_TAG} (package ${PACKAGE_VERSION})"
  exit 0
fi

NEW_VERSION="$(bump_minor_reset_patch "${PACKAGE_VERSION}")"

write_version_file "$NEW_VERSION" "$HERMES_TAG"
pin_agent_base "$HERMES_TAG"
pin_dockerfile_hermes "$HERMES_TAG" Dockerfile

echo "[bump-hermes] ${PACKAGE_VERSION} → ${NEW_VERSION} on hermes ${HERMES_TAG}"
echo "[bump-hermes] updated VERSION (hermes-base + agent-base) and Dockerfile HERMES_IMAGE pin"
echo "[bump-hermes] next: review vendor sync, run ./scripts/smoke.sh, commit and tag v${NEW_VERSION}"
