#!/usr/bin/env sh
# Write the root VERSION file (line 1: x.y.z, line 2: hermes-base=v…).
# Usage: scripts/set-version.sh 0.4.0 [v2026.6.5]
#        scripts/set-version.sh v0.4.0 v2026.6.5

set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"

semver="${1:?Usage: scripts/set-version.sh <x.y.z> [hermes-base-tag]}"
hermes_base="${2:-}"

semver="${semver#v}"
case "$semver" in
*.*.*) ;;
*)
	printf '%s\n' "Expected x.y.z (e.g. 0.4.0), got: $1" >&2
	exit 1
	;;
esac

if [ -n "$hermes_base" ]; then
	hermes_base="${hermes_base#v}"
	hermes_base="v${hermes_base}"
fi

{
	printf '%s\n' "$semver"
	if [ -n "$hermes_base" ]; then
		printf 'hermes-base=%s\n' "$hermes_base"
	fi
} >"${ROOT_DIR}/VERSION"

if [ -n "$hermes_base" ]; then
	python3 - "$hermes_base" "${ROOT_DIR}/Dockerfile" <<'PY'
import pathlib
import re
import sys

tag, dockerfile = sys.argv[1], pathlib.Path(sys.argv[2])
text = dockerfile.read_text()
new_line = f"ARG HERMES_IMAGE=nousresearch/hermes-agent:{tag}"
updated, count = re.subn(r"^ARG HERMES_IMAGE=.*", new_line, text, count=1, flags=re.MULTILINE)
if count != 1:
    raise SystemExit(f"could not update HERMES_IMAGE in {dockerfile}")
dockerfile.write_text(updated)
PY
fi

printf '%s\n' "Wrote VERSION=${semver} hermes-base=${hermes_base:-unchanged} → tag v${semver} on release."
