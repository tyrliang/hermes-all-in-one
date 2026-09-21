#!/usr/bin/env bash
# Upgrade-survival matrix for docker/patches/apply-agent-patches.sh.
#
# The script guards a local patch that upstream does not carry. Every scenario
# below is a real path a release can take. The property under test is narrow:
#
#   the build NEVER goes green with the patch missing from the image
#
# S2 is why this file exists. An earlier version of the script compared the
# target against the SOURCE, so after a vendor refresh reverted our patch both
# sides held upstream's file, compared equal, and reported "already applied" —
# green build, fix gone, no signal anywhere.
#
# Run: bash docker/patches/test-apply-agent-patches.sh
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$ROOT/docker/patches/apply-agent-patches.sh"
REL="tools/mcp_tool_transport.py"
MARKER="_env_proxy_for"          # present only in the patched file

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

PATCHED="$WORK/patched.py"
BASE="$WORK/base.py"
NEWER="$WORK/newer.py"

cp "$ROOT/vendor/hermes-agent/$REL" "$PATCHED"

# Reconstruct the pinned base version from the hash recorded in the script:
# strip our patch back out is fragile, so pull the pre-patch blob from git.
BASE_SHA="$(awk '$1 == "tools/mcp_tool_transport.py" {print $2}' "$SCRIPT")"
PATCHED_SHA="$(awk '$1 == "tools/mcp_tool_transport.py" {print $3}' "$SCRIPT")"

found=""
while read -r sha; do
    [ -n "$sha" ] || continue
    if git -C "$ROOT" cat-file -p "$sha:vendor/hermes-agent/$REL" 2>/dev/null \
        | sha256sum | cut -d' ' -f1 | grep -qx "$BASE_SHA"; then
        found="$sha"
        break
    fi
done < <(git -C "$ROOT" log --format=%H -- "vendor/hermes-agent/$REL" 2>/dev/null)

if [ -z "$found" ]; then
    echo "SKIP: cannot locate the pre-patch blob in git history"
    echo "      (shallow clone?) — matrix needs it to simulate upstream"
    exit 0
fi
git -C "$ROOT" cat-file -p "$found:vendor/hermes-agent/$REL" > "$BASE"

# A hypothetical newer upstream: still unpatched, but changed.
cp "$BASE" "$NEWER"
printf '\n# upstream: unrelated change in a later release\n' >> "$NEWER"

pass=0
fail=0

scenario() { # name  base-image-file  vendored-file  want_rc  want_fix
    local name="$1" tgt="$2" src="$3" want_rc="$4" want_fix="$5"
    rm -rf "$WORK/agent" "$WORK/src"
    mkdir -p "$WORK/agent/$(dirname "$REL")" "$WORK/src/$(dirname "$REL")"
    cp "$tgt" "$WORK/agent/$REL"
    cp "$src" "$WORK/src/$REL"

    local out rc fix
    out="$(AGENT_ROOT="$WORK/agent" PATCH_SRC="$WORK/src" bash "$SCRIPT" 2>&1)"
    rc=$?
    if grep -q "$MARKER" "$WORK/agent/$REL"; then fix=present; else fix=gone; fi

    # The invariant: a green build must leave the patch in place.
    if [ "$rc" -eq 0 ] && [ "$fix" = gone ]; then
        echo "  FAIL  $name — SILENT REGRESSION (green build, patch missing)"
        echo "$out" | sed 's/^/          /'
        fail=$((fail + 1))
        return
    fi
    if [ "$rc" -eq "$want_rc" ] && [ "$fix" = "$want_fix" ]; then
        echo "  PASS  $name (rc=$rc, patch $fix)"
        pass=$((pass + 1))
    else
        echo "  FAIL  $name — want rc=$want_rc/$want_fix, got rc=$rc/$fix"
        echo "$out" | sed 's/^/          /'
        fail=$((fail + 1))
    fi
}

echo "sanity: recorded hashes match the files on disk"
if [ "$(sha256sum "$PATCHED" | cut -d' ' -f1)" = "$PATCHED_SHA" ]; then
    echo "  PASS  vendored file matches the recorded patched hash"
    pass=$((pass + 1))
else
    echo "  FAIL  vendored file does not match the recorded patched hash"
    echo "        update PATCHES in apply-agent-patches.sh"
    fail=$((fail + 1))
fi

echo
echo "upgrade matrix"
# name                                   target   source    rc  fix
scenario "S0 pristine base, patch present"  "$BASE"    "$PATCHED" 0 present
scenario "S1 hermes-base moved"             "$NEWER"   "$PATCHED" 1 gone
scenario "S2 vendor refresh reverted patch"  "$BASE"    "$BASE"    1 gone
scenario "S3 vendor refresh + base moved"    "$NEWER"   "$NEWER"   1 gone
scenario "S4 rebuild of a patched image"     "$PATCHED" "$PATCHED" 0 present

echo
echo "error cases"
rm -rf "$WORK/agent" "$WORK/src"
mkdir -p "$WORK/agent/$(dirname "$REL")" "$WORK/src/$(dirname "$REL")"
cp "$BASE" "$WORK/agent/$REL"
out="$(AGENT_ROOT="$WORK/agent" PATCH_SRC="$WORK/src" bash "$SCRIPT" 2>&1)"; rc=$?
if [ $rc -ne 0 ] && echo "$out" | grep -q "patched source missing"; then
    echo "  PASS  missing source fails loudly"; pass=$((pass + 1))
else
    echo "  FAIL  missing source (rc=$rc)"; fail=$((fail + 1))
fi

rm -rf "$WORK/agent" "$WORK/src"
mkdir -p "$WORK/agent/$(dirname "$REL")" "$WORK/src/$(dirname "$REL")"
cp "$PATCHED" "$WORK/src/$REL"
out="$(AGENT_ROOT="$WORK/agent" PATCH_SRC="$WORK/src" bash "$SCRIPT" 2>&1)"; rc=$?
if [ $rc -ne 0 ] && echo "$out" | grep -q "target missing in base image"; then
    echo "  PASS  missing target fails loudly"; pass=$((pass + 1))
else
    echo "  FAIL  missing target (rc=$rc)"; fail=$((fail + 1))
fi

echo
echo "RESULT: $pass passed, $fail failed"
[ "$fail" -eq 0 ] || exit 1
