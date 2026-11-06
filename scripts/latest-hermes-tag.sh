#!/usr/bin/env bash
# Print the newest nousresearch/hermes-agent image tag (vX.Y.Z) or fail loudly.
#
# Upstream changed tag scheme on 2026-11-05: image tags used to be CalVer
# (v2026.9.24) and are now semver (v0.23.0). The two schemes are not comparable
# numerically — v2026.9.24 > v0.23.0 as a version tuple — so "sort everything and
# take the max" silently returns a stale CalVer tag forever.
#
# Resolution order:
#   1. GitHub `releases/latest` — the authoritative "current release", whatever
#      its scheme. The tag is only accepted if Docker Hub actually publishes an
#      image for it, so a release with no image never becomes a base pin.
#   2. Docker Hub tag scan (both schemes) — used only when GitHub cannot be
#      asked. Ranks semver-shaped tags above CalVer-shaped ones, because CalVer
#      is the superseded scheme; within a scheme the higher version wins.
#   3. Neither path produced a validated tag → exit 1 with a diagnostic. Never
#      print an unvalidated or stale tag.
#
# Dependency-free: python3 stdlib only, no gh/curl required at runtime. Set
# GH_TOKEN or GITHUB_TOKEN to lift GitHub's anonymous rate limit; the token is
# read from the environment and never printed.
set -euo pipefail

python3 <<'PY'
import json
import os
import re
import sys
import urllib.error
import urllib.request

REPO = "NousResearch/hermes-agent"
GH_RELEASES_LATEST = os.environ.get(
    "HERMES_GH_RELEASES_LATEST",
    f"https://api.github.com/repos/{REPO}/releases/latest",
)
DOCKER_TAG = "https://hub.docker.com/v2/repositories/nousresearch/hermes-agent/tags/{tag}"
DOCKER_TAGS = (
    "https://hub.docker.com/v2/repositories/nousresearch/hermes-agent/tags"
    "?page_size=100&ordering=-last_updated&page={page}"
)
TIMEOUT = 30
MAX_PAGES = 5

# vX.Y.Z or vX.Y.Z.W. Anchored so "latest", "main", "edge" and digest tags never match.
VERSION_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?$")
# CalVer shape used through 2026-11: a 4-digit year as the first component.
CALVER_MAJOR = re.compile(r"^v(20\d\d)\.")


def _get_json(url):
    request = urllib.request.Request(url)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("User-Agent", "hermes-all-in-one/latest-hermes-tag")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.load(response)


def _version(tag):
    match = VERSION_TAG.match(tag)
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())


def _scheme_rank(tag):
    """Semver-shaped tags outrank CalVer-shaped ones: CalVer is retired upstream."""
    return 0 if CALVER_MAJOR.match(tag) else 1


def docker_hub_has_image(tag):
    """True only if Docker Hub serves an active image for exactly this tag."""
    try:
        data = _get_json(DOCKER_TAG.format(tag=tag))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False, "no such Docker Hub tag (HTTP 404)"
        return False, f"Docker Hub tag lookup failed (HTTP {exc.code})"
    except Exception as exc:  # noqa: BLE001 - any transport failure means "unknown"
        return False, f"Docker Hub tag lookup failed ({exc.__class__.__name__}: {exc})"

    status = data.get("tag_status") or data.get("status")
    if status and status != "active":
        return False, f"Docker Hub tag status is {status!r}"
    if not data.get("name"):
        return False, "Docker Hub returned no tag name"
    return True, "Docker Hub tag is active"


def from_github_release():
    data = _get_json(GH_RELEASES_LATEST)
    tag = (data.get("tag_name") or "").strip()
    if not tag:
        raise ValueError("release has no tag_name")
    if not VERSION_TAG.match(tag):
        raise ValueError(f"release tag {tag!r} is not a vX.Y.Z version tag")
    return tag


def from_docker_hub_scan():
    seen = {}
    for page in range(1, MAX_PAGES + 1):
        data = _get_json(DOCKER_TAGS.format(page=page))
        results = data.get("results") or []
        for item in results:
            name = (item.get("name") or "").strip()
            if not name or name in seen:
                continue
            if VERSION_TAG.match(name):
                seen[name] = item
        if not results or not data.get("next"):
            break
    if not seen:
        raise ValueError("no vX.Y.Z tags found on Docker Hub")
    ranked = sorted(
        seen,
        key=lambda tag: (_scheme_rank(tag), _version(tag)),
        reverse=True,
    )
    return ranked[0]


def main():
    problems = []

    tag = None
    try:
        candidate = from_github_release()
    except Exception as exc:  # noqa: BLE001
        problems.append(f"GitHub releases/latest: {exc}")
    else:
        ok, detail = docker_hub_has_image(candidate)
        if ok:
            tag = candidate
        else:
            problems.append(f"GitHub releases/latest says {candidate}, but {detail}")

    if tag is None:
        try:
            candidate = from_docker_hub_scan()
        except Exception as exc:  # noqa: BLE001
            problems.append(f"Docker Hub tag scan: {exc}")
        else:
            ok, detail = docker_hub_has_image(candidate)
            if ok:
                tag = candidate
            else:
                problems.append(f"Docker Hub tag scan ranked {candidate}, but {detail}")

    if tag is None:
        print(
            "latest-hermes-tag: cannot establish the latest "
            "nousresearch/hermes-agent image tag. Refusing to print a "
            "possibly-stale tag.",
            file=sys.stderr,
        )
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print(
            "  Pass an explicit tag instead (scripts/bump-hermes.sh vX.Y.Z) and "
            "pin it only after checking "
            "https://hub.docker.com/r/nousresearch/hermes-agent/tags",
            file=sys.stderr,
        )
        return 1

    print(tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
PY
