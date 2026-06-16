#!/usr/bin/env bash
# Shared VERSION file helpers. Source from other scripts: . "$(dirname "$0")/version-lib.sh"

VERSION_FILE="${VERSION_FILE:-VERSION}"

read_version_file() {
  local root="${1:-.}"
  local file="${root%/}/${VERSION_FILE}"

  if [[ ! -f "$file" ]]; then
    echo "[version] missing ${file}" >&2
    return 1
  fi

  PACKAGE_VERSION="$(grep -Ev '^\s*(#|$)' "$file" | head -1 | tr -d ' \t\r\n')"
  PACKAGE_VERSION="${PACKAGE_VERSION#v}"
  case "$PACKAGE_VERSION" in
    *.*.*) ;;
    *)
      echo "[version] expected x.y.z on first line, got: ${PACKAGE_VERSION}" >&2
      return 1
      ;;
  esac

  HERMES_BASE="$(grep -E '^hermes-base=' "$file" | head -1 | cut -d= -f2- | tr -d ' \t\r\n' || true)"
  if [[ -n "$HERMES_BASE" && "$HERMES_BASE" != v* ]]; then
    HERMES_BASE="v${HERMES_BASE}"
  fi

  # Pinned upstream tag for the vendored hermes-agent subtree.
  # shellcheck disable=SC2034  # consumed by scripts that source this lib
  AGENT_BASE="$(grep -E '^agent-base=' "$file" | head -1 | cut -d= -f2- | tr -d ' \t\r\n' || true)"

  # Pinned upstream ref (tag or commit sha) for the vendored hermes-webui
  # subtree. Empty when unset — sync falls back to tracking the branch head.
  # Not normalised to a 'v' prefix: it may be a bare commit sha.
  # shellcheck disable=SC2034  # consumed by scripts that source this lib
  WEBUI_BASE="$(grep -E '^webui-base=' "$file" | head -1 | cut -d= -f2- | tr -d ' \t\r\n' || true)"
}

write_version_file() {
  local pkg="$1"
  local hermes_base="${2:-}"
  local file="${3:-${VERSION_FILE}}"

  pkg="${pkg#v}"
  case "$pkg" in
    *.*.*) ;;
    *)
      echo "[version] expected x.y.z, got: ${pkg}" >&2
      return 1
      ;;
  esac

  if [[ -n "$hermes_base" ]]; then
    hermes_base="${hermes_base#v}"
    hermes_base="v${hermes_base}"
  fi

  # Preserve the existing agent-base and webui-base pins — version bumps must
  # not silently drop them (mirrors the hermes-base preservation contract).
  local agent_base=""
  local webui_base=""
  if [[ -f "$file" ]]; then
    agent_base="$(grep -E '^agent-base=' "$file" | head -1 | cut -d= -f2- | tr -d ' \t\r\n' || true)"
    webui_base="$(grep -E '^webui-base=' "$file" | head -1 | cut -d= -f2- | tr -d ' \t\r\n' || true)"
  fi

  {
    printf '%s\n' "$pkg"
    if [[ -n "$hermes_base" ]]; then
      printf 'hermes-base=%s\n' "$hermes_base"
    fi
    if [[ -n "$agent_base" ]]; then
      printf 'agent-base=%s\n' "$agent_base"
    fi
    if [[ -n "$webui_base" ]]; then
      printf 'webui-base=%s\n' "$webui_base"
    fi
  } >"$file"
}

pin_dockerfile_hermes() {
  local hermes_tag="$1"
  local dockerfile="${2:-Dockerfile}"

  hermes_tag="${hermes_tag#v}"
  hermes_tag="v${hermes_tag}"

  python3 - "$hermes_tag" "$dockerfile" <<'PY'
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
}

pin_agent_base() {
  # Set (or insert) the agent-base pin in the VERSION file. Tag.
  local ref="$1"
  local file="${2:-${VERSION_FILE}}"

  python3 - "$ref" "$file" <<'PY'
import pathlib
import re
import sys

ref, file = sys.argv[1], pathlib.Path(sys.argv[2])
text = file.read_text()
if re.search(r"(?m)^agent-base=.*$", text):
    text = re.sub(r"(?m)^agent-base=.*$", f"agent-base={ref}", text, count=1)
else:
    # Insert after hermes-base= line if present, else after first line
    if re.search(r"(?m)^hermes-base=.*$", text):
        text = re.sub(r"(?m)^(hermes-base=.*)", r"\1\nagent-base=" + ref, text, count=1)
    else:
        lines = text.splitlines(keepends=True)
        lines.insert(1, f"agent-base={ref}\n")
        text = "".join(lines)
file.write_text(text)
PY
}

pin_webui_base() {
  # Set (or insert) the webui-base pin in the VERSION file. Tag or sha.
  local ref="$1"
  local file="${2:-${VERSION_FILE}}"

  python3 - "$ref" "$file" <<'PY'
import pathlib
import re
import sys

ref, file = sys.argv[1], pathlib.Path(sys.argv[2])
text = file.read_text()
if re.search(r"(?m)^webui-base=.*$", text):
    text = re.sub(r"(?m)^webui-base=.*$", f"webui-base={ref}", text, count=1)
else:
    if not text.endswith("\n"):
        text += "\n"
    text += f"webui-base={ref}\n"
file.write_text(text)
PY
}

bump_minor_reset_patch() {
  local current="$1"
  local x y z
  IFS=. read -r x y z <<<"$current"
  y=$((y + 1))
  printf '%s.%s.0' "$x" "$y"
}

bump_patch() {
  local current="$1"
  local x y z
  IFS=. read -r x y z <<<"$current"
  z=$((z + 1))
  printf '%s.%s.%s' "$x" "$y" "$z"
}
