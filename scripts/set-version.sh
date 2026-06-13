#!/usr/bin/env bash
# Write the root VERSION file (line 1: x.y.z, line 2: hermes-base=v…).
# When hermes-base is omitted, the existing pin in VERSION is preserved.
# Usage: scripts/set-version.sh 0.4.0 [v2026.6.5]
#        scripts/set-version.sh v0.4.0 v2026.6.5

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

# shellcheck source=scripts/version-lib.sh
. "${ROOT_DIR}/scripts/version-lib.sh"

semver="${1:?Usage: scripts/set-version.sh <x.y.z> [hermes-base-tag]}"
hermes_arg="${2:-}"

semver="${semver#v}"
case "$semver" in
*.*.*) ;;
*)
	printf '%s\n' "Expected x.y.z (e.g. 0.4.0), got: $1" >&2
	exit 1
	;;
esac

if [[ -n "$hermes_arg" ]]; then
	hermes_base="${hermes_arg#v}"
	hermes_base="v${hermes_base}"
	pin_dockerfile_hermes "$hermes_base"
else
	read_version_file "$ROOT_DIR"
	hermes_base="${HERMES_BASE:-}"
fi

write_version_file "$semver" "$hermes_base"

printf '%s\n' "Wrote VERSION=${semver} hermes-base=${hermes_base:-unset} → tag v${semver} on release."
