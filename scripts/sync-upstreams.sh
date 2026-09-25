#!/usr/bin/env bash
# Resolve the pinned WebUI tag to the commit SHA the image fetches.
# Does not vendor. Agent bytes come from the Docker base image.
# Vault is not part of this image.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

# shellcheck source=scripts/version-lib.sh
. "${ROOT_DIR}/scripts/version-lib.sh"
read_version_file "$ROOT_DIR"

if [[ -z "${WEBUI_BASE:-}" ]]; then
  echo "[sync] webui-base is unset" >&2
  exit 1
fi

sha="$(git ls-remote https://github.com/nesquena/hermes-webui.git "refs/tags/${WEBUI_BASE}^{}" | awk '{print $1}')"
if [[ -z "$sha" ]]; then
  sha="$(git ls-remote https://github.com/nesquena/hermes-webui.git "refs/tags/${WEBUI_BASE}" | awk '{print $1}')"
fi
if [[ ! "$sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "[sync] could not resolve ${WEBUI_BASE} to a commit" >&2
  exit 1
fi

if [[ "${WEBUI_SHA:-}" == "$sha" ]]; then
  echo "[sync] webui-sha already ${sha} (${WEBUI_BASE})"
  exit 0
fi

pin_webui_sha "$sha"
echo "[sync] webui-sha ${WEBUI_SHA:-unset} -> ${sha} for ${WEBUI_BASE}"
echo "[sync] image fetches https://github.com/nesquena/hermes-webui/archive/${sha}.tar.gz"
