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
# Each entry pins the sha256 of the file AS IT SHIPS IN THE PINNED BASE IMAGE.
# On a hermes-base bump the upstream file changes, the recorded hash stops
# matching, and this script FAILS THE BUILD rather than pasting a stale patched
# file over newer upstream code. That is deliberate: a silent no-op (or a silent
# revert of upstream fixes) is far worse than a red build. When it fires, re-do
# the patch against the new base and update the hash.
#
# Log markers, greppable in build output:
#   agent-patch: applied <path>
#   agent-patch: already applied <path>
#   agent-patch: FAILED <path>        <- alert
set -euo pipefail

AGENT_ROOT="${AGENT_ROOT:-/opt/hermes}"
PATCH_SRC="${PATCH_SRC:-/app/patches/agent}"

# path-under-agent-root : sha256 of that file in the pinned base image
#
# Refresh a hash after intentionally re-basing a patch:
#   docker run --rm nousresearch/hermes-agent:<tag> \
#     sha256sum /opt/hermes/tools/mcp_tool_transport.py
PATCHES="
tools/mcp_tool_transport.py 691901e3bee4c8f49975b77a802a146d28c3970963753fbc539bb1a30809b3a2
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

while read -r rel want_base; do
    [ -n "${rel:-}" ] || continue

    target="${AGENT_ROOT}/${rel}"
    source="${PATCH_SRC}/${rel}"

    [ -f "$source" ] || fail "$rel" \
        "patched source missing: $source" \
        "the Dockerfile must COPY vendor/hermes-agent/${rel} to that path"

    [ -f "$target" ] || fail "$rel" \
        "target missing in base image: $target" \
        "upstream moved or removed this file; re-target the patch"

    have_target="$(sha256sum "$target" | cut -d' ' -f1)"
    have_source="$(sha256sum "$source" | cut -d' ' -f1)"

    if [ "$have_target" = "$have_source" ]; then
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
            "upstream changes to this file. Re-apply the patch against the new" \
            "base, refresh vendor/hermes-agent/${rel}, and update the hash in" \
            "docker/patches/apply-agent-patches.sh."
    fi

    cp "$source" "$target"
    chmod 644 "$target"

    check="$(sha256sum "$target" | cut -d' ' -f1)"
    [ "$check" = "$have_source" ] || fail "$rel" \
        "post-copy verification failed (wrote ${check}, wanted ${have_source})"

    # Drop any bytecode the base image compiled from the pre-patch source.
    rm -f "$(dirname "$target")/__pycache__/$(basename "$target" .py)".*.pyc

    echo "agent-patch: applied ${rel}"
    applied=$((applied + 1))
done <<EOF
$(echo "$PATCHES" | sed '/^[[:space:]]*$/d;/^[[:space:]]*#/d')
EOF

echo "agent-patch: done (${applied} applied, ${skipped} already present)"
