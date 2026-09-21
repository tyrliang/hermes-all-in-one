#!/usr/bin/env bash
# Apply local patches onto the agent tree that ships inside the base image.
#
# Why this exists
# ---------------
# /opt/hermes comes wholesale from nousresearch/hermes-agent. The Dockerfile
# copies vendor/hermes-webui and vendor/hermes-vault into the image, but NOT
# vendor/hermes-agent — that tree is a read-only reference used by
# scripts/patch-vendor-models.py. So a fix committed to vendor/hermes-agent
# ships nothing on its own. This script installs the handful of agent files we
# carry a local patch for, straight onto the base image's copy.
#
# Fail-loud contract
# ------------------
# Each entry pins TWO hashes: the file as it ships in the pinned BASE image,
# and our PATCHED version of it. Both are load-bearing, and they guard
# different failure modes:
#
#   base hash    — the target changed, so hermes-base moved. Overwriting would
#                  revert whatever upstream changed in that file.
#   patched hash — the SOURCE changed, so a vendor refresh reverted our patch
#                  in vendor/hermes-agent. Without this check a refresh leaves
#                  target and source both holding upstream's unpatched file;
#                  they compare equal, the script reports "already applied",
#                  the build goes green, and the fix is silently gone. That is
#                  the exact class of silent no-op this script exists to stop,
#                  so the source is verified BEFORE any equality shortcut.
#
# Either mismatch fails the build. A red build costs minutes; a silent revert
# costs a production outage and a debugging session months later.
#
# Log markers, greppable in build output:
#   agent-patch: applied <path>
#   agent-patch: already applied <path>
#   agent-patch: FAILED <path>        <- alert
set -euo pipefail

AGENT_ROOT="${AGENT_ROOT:-/opt/hermes}"
PATCH_SRC="${PATCH_SRC:-/app/patches/agent}"

# <path under agent root> <sha256 in pinned base image> <sha256 of our patched file>
#
# Refresh the base hash after intentionally re-basing a patch:
#   docker run --rm nousresearch/hermes-agent:<tag> \
#     sha256sum /opt/hermes/tools/mcp_tool_transport.py
# Refresh the patched hash from the vendored tree:
#   sha256sum vendor/hermes-agent/tools/mcp_tool_transport.py
PATCHES="
tools/mcp_tool_transport.py 691901e3bee4c8f49975b77a802a146d28c3970963753fbc539bb1a30809b3a2 64c4e32e3b2cc4f25bb96f38ea9aaeca4d2d61a2100ac3a39890fe4f5edee684
"

fail() {
    echo "agent-patch: FAILED $1" >&2
    shift
    for line in "$@"; do
        echo "  $line" >&2
    done
    exit 1
}

applied=0
skipped=0

while read -r rel want_base want_patched; do
    [ -n "${rel:-}" ] || continue

    target="${AGENT_ROOT}/${rel}"
    source="${PATCH_SRC}/${rel}"

    [ -f "$source" ] || fail "$rel" \
        "patched source missing: $source" \
        "the Dockerfile must COPY vendor/hermes-agent/${rel} to that path"

    [ -f "$target" ] || fail "$rel" \
        "target missing in base image: $target" \
        "upstream moved or removed this file; re-target the patch"

    have_source="$(sha256sum "$source" | cut -d' ' -f1)"
    have_target="$(sha256sum "$target" | cut -d' ' -f1)"

    # Verify the SOURCE first. A vendor refresh (subtree pull or archive
    # replace) rewrites vendor/hermes-agent from upstream and silently drops
    # the local patch. Checking this before the equality shortcut below is what
    # turns that into a red build instead of a green no-op.
    if [ "$have_source" != "$want_patched" ]; then
        if [ "$have_source" = "$want_base" ]; then
            fail "$rel" \
                "vendored source is UNPATCHED upstream code." \
                "" \
                "A vendor refresh reverted vendor/hermes-agent/${rel}." \
                "Re-apply the local patch to that file, commit it, and rebuild." \
                "See docker/patches/README.md and the release skill's" \
                "'Local patches registry'."
        fi
        fail "$rel" \
            "vendored source matches neither the patched nor the base hash." \
            "expected patched: ${want_patched}" \
            "actual:           ${have_source}" \
            "" \
            "Either the patch was edited without updating its hash, or a vendor" \
            "refresh brought a new upstream file. Re-base the patch and update" \
            "both hashes in docker/patches/apply-agent-patches.sh."
    fi

    if [ "$have_target" = "$want_patched" ]; then
        echo "agent-patch: already applied ${rel}"
        skipped=$((skipped + 1))
        continue
    fi

    if [ "$have_target" != "$want_base" ]; then
        fail "$rel" \
            "base image file does not match the recorded pre-patch hash." \
            "expected: ${want_base}" \
            "actual:   ${have_target}" \
            "" \
            "hermes-base almost certainly moved. Overwriting now would revert" \
            "upstream changes to this file. Check whether upstream fixed the bug" \
            "(then drop the patch); otherwise re-apply the patch against the new" \
            "base, refresh vendor/hermes-agent/${rel}, and update both hashes in" \
            "docker/patches/apply-agent-patches.sh."
    fi

    cp "$source" "$target"
    chmod 644 "$target"

    check="$(sha256sum "$target" | cut -d' ' -f1)"
    [ "$check" = "$want_patched" ] || fail "$rel" \
        "post-copy verification failed (wrote ${check}, wanted ${want_patched})"

    # Drop any bytecode the base image compiled from the pre-patch source.
    rm -f "$(dirname "$target")/__pycache__/$(basename "$target" .py)".*.pyc

    echo "agent-patch: applied ${rel}"
    applied=$((applied + 1))
done <<EOF
$(echo "$PATCHES" | sed '/^[[:space:]]*$/d;/^[[:space:]]*#/d')
EOF

echo "agent-patch: done (${applied} applied, ${skipped} already present)"
