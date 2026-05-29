#!/usr/bin/env sh
# Write the root VERSION file CI uses for the GHCR tag (prefix v on publish).
# Usage: scripts/set-version.sh 0.0.4
#        scripts/set-version.sh v1.2.3   # leading v is stripped before writing file

set -eu

semver="${1:?Usage: scripts/set-version.sh <major.minor.patch>}"

semver="${semver#v}"

case "$semver" in
*.*.*) ;;
*)
	printf '%s\n' "Expected at least major.minor.patch (e.g. 1.0.0 or v1.0.0), got: $1" >&2
	exit 1
	;;
esac

printf '%s\n' "$semver" > VERSION

printf '%s\n' "Wrote VERSION=$semver → GHCR tag will be v${semver} on next publish (push main or workflow_dispatch)."
