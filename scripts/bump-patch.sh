#!/usr/bin/env bash
# Bump patch (z) for all-in-one-only changes; hermes-base and Dockerfile pin unchanged.
# Usage: scripts/bump-patch.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

# shellcheck source=scripts/version-lib.sh
. "${ROOT_DIR}/scripts/version-lib.sh"

read_version_file "$ROOT_DIR"

NEW_VERSION="$(bump_patch "${PACKAGE_VERSION}")"
write_version_file "$NEW_VERSION" "${HERMES_BASE}"

echo "[bump-patch] ${PACKAGE_VERSION} → ${NEW_VERSION} (hermes-base=${HERMES_BASE:-unset})"
echo "[bump-patch] next: run ./scripts/smoke.sh, commit and tag v${NEW_VERSION}"
