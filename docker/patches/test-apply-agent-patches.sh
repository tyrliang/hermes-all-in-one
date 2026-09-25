#!/usr/bin/env bash
# Upgrade-survival matrix for docker/patches/apply-agent-patches.sh.
#
# The script guards local patches that upstream does not carry. Every scenario
# below is a real path a release can take. The property under test is narrow:
#
#   the build NEVER goes green with the patch missing from the image
#
# S2 is why this file exists. An earlier version of the script compared the
# target against the SOURCE, so after a vendor refresh reverted our patch both
# sides held upstream's file, compared equal, and reported "already applied" —
# green build, fix gone, no signal anywhere.
#
# The matrix runs on a SYNTHETIC patch table injected through PATCHES_OVERRIDE,
# so the guard stays tested while the real table is empty (upstream absorbed the
# only entry in hermes-base v2026.9.24). The real table, when non-empty, is
# checked separately below against the vendored files it names.
#
# Run: bash docker/patches/test-apply-agent-patches.sh
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$ROOT/docker/patches/apply-agent-patches.sh"
REL="tools/synthetic_patch_target.py"
MARKER="_local_patch_marker"     # present only in the patched file

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

PATCHED="$WORK/patched.py"
BASE="$WORK/base.py"
NEWER="$WORK/newer.py"

# Upstream's file as it ships in the pinned base image.
cat > "$BASE" <<'PY'
"""Stand-in for an agent module we carry a local patch against."""


def connect(url: str) -> str:
    return url
PY

# Our patched version of it.
cp "$BASE" "$PATCHED"
cat >> "$PATCHED" <<'PY'


def _local_patch_marker() -> bool:
    return True
PY

# A hypothetical newer upstream: still unpatched, but changed.
cp "$BASE" "$NEWER"
printf '\n# upstream: unrelated change in a later release\n' >> "$NEWER"

sha() { sha256sum "$1" | cut -d' ' -f1; }
TABLE="$REL $(sha "$BASE") $(sha "$PATCHED")"

pass=0
fail=0

scenario() { # name  base-image-file  vendored-file  want_rc  want_fix
    local name="$1" tgt="$2" src="$3" want_rc="$4" want_fix="$5"
    rm -rf "$WORK/agent" "$WORK/src"
    mkdir -p "$WORK/agent/$(dirname "$REL")" "$WORK/src/$(dirname "$REL")"
    cp "$tgt" "$WORK/agent/$REL"
    cp "$src" "$WORK/src/$REL"

    local out rc fix
    out="$(PATCHES_OVERRIDE="$TABLE" AGENT_ROOT="$WORK/agent" PATCH_SRC="$WORK/src" bash "$SCRIPT" 2>&1)"
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

echo "sanity: registered patches match the vendored files they name"
registered=0
while read -r rel _want_base want_patched; do
    [ -n "${rel:-}" ] || continue
    case "$rel" in \#*) continue ;; esac
    registered=$((registered + 1))
    if [ ! -f "$ROOT/vendor/hermes-agent/$rel" ]; then
        echo "  FAIL  $rel — no such file under vendor/hermes-agent"
        fail=$((fail + 1))
        continue
    fi
    if [ "$(sha "$ROOT/vendor/hermes-agent/$rel")" = "$want_patched" ]; then
        echo "  PASS  $rel matches its recorded patched hash"
        pass=$((pass + 1))
    else
        echo "  FAIL  $rel does not match its recorded patched hash"
        echo "        re-apply the patch or update PATCHES in apply-agent-patches.sh"
        fail=$((fail + 1))
    fi
done < <(sed -n '/^PATCHES="$/,/^"$/p' "$SCRIPT" | sed '1d;$d;/^[[:space:]]*$/d')
if [ "$registered" -eq 0 ]; then
    echo "  none registered — matrix below runs on a synthetic patch"
fi

echo
echo "upgrade matrix (synthetic patch)"
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
out="$(PATCHES_OVERRIDE="$TABLE" AGENT_ROOT="$WORK/agent" PATCH_SRC="$WORK/src" bash "$SCRIPT" 2>&1)"; rc=$?
if [ $rc -ne 0 ] && echo "$out" | grep -q "patched source missing"; then
    echo "  PASS  missing source fails loudly"; pass=$((pass + 1))
else
    echo "  FAIL  missing source (rc=$rc)"; fail=$((fail + 1))
fi

rm -rf "$WORK/agent" "$WORK/src"
mkdir -p "$WORK/agent/$(dirname "$REL")" "$WORK/src/$(dirname "$REL")"
cp "$PATCHED" "$WORK/src/$REL"
out="$(PATCHES_OVERRIDE="$TABLE" AGENT_ROOT="$WORK/agent" PATCH_SRC="$WORK/src" bash "$SCRIPT" 2>&1)"; rc=$?
if [ $rc -ne 0 ] && echo "$out" | grep -q "target missing in base image"; then
    echo "  PASS  missing target fails loudly"; pass=$((pass + 1))
else
    echo "  FAIL  missing target (rc=$rc)"; fail=$((fail + 1))
fi

echo
echo "empty table"
rm -rf "$WORK/agent" "$WORK/src"; mkdir -p "$WORK/agent" "$WORK/src"
out="$(PATCHES_OVERRIDE=$'\n' AGENT_ROOT="$WORK/agent" PATCH_SRC="$WORK/src" bash "$SCRIPT" 2>&1)"; rc=$?
if [ $rc -eq 0 ] && echo "$out" | grep -q "done (0 applied"; then
    echo "  PASS  no registered patches is a clean no-op"; pass=$((pass + 1))
else
    echo "  FAIL  empty table (rc=$rc): $out"; fail=$((fail + 1))
fi

echo
echo "RESULT: $pass passed, $fail failed"
[ "$fail" -eq 0 ] || exit 1
