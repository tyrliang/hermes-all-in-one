#!/usr/bin/env bash
# Print the newest nousresearch/hermes-agent CalVer tag on Docker Hub (v20*).
set -euo pipefail

python3 - <<'PY'
import json
import re
import urllib.request

url = "https://hub.docker.com/v2/repositories/nousresearch/hermes-agent/tags?page_size=100&ordering=-last_updated"
with urllib.request.urlopen(url, timeout=30) as response:
    data = json.load(response)


def key(tag: str) -> tuple[int, ...]:
    match = re.match(r"^v(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?$", tag)
    if not match:
        return (0, 0, 0, 0)
    return tuple(int(part or 0) for part in match.groups())

tags = [item["name"] for item in data.get("results", []) if re.match(r"^v20", item.get("name", ""))]
if not tags:
    raise SystemExit("no v20* hermes-agent tags found on Docker Hub")
tags.sort(key=key, reverse=True)
print(tags[0])
PY
