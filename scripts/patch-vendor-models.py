#!/usr/bin/env python3
"""
Post-sync patch: keep hermes-webui model lists in sync with hermes-agent.

Sources:
  - OPENROUTER_MODELS (models_catalog_static.py, re-exported by models.py)
      → _FALLBACK_MODELS (all providers)
  - DEFAULT_CODEX_MODELS (codex_models.py)
      → _PROVIDER_MODELS openai + openai-codex

Idempotent — safe to run multiple times.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
# v0.21.1+ keeps curated tables in models_catalog_static; models.py re-exports.
AGENT_MODELS_CATALOG = ROOT / "vendor/hermes-agent/hermes_cli/models_catalog_static.py"
AGENT_MODELS = ROOT / "vendor/hermes-agent/hermes_cli/models.py"
AGENT_CODEX = ROOT / "vendor/hermes-agent/hermes_cli/codex_models.py"
WEBUI_CONFIG = ROOT / "vendor/hermes-webui/api/config.py"

# provider-prefix → display name used in webui _FALLBACK_MODELS
PROVIDER_MAP: dict[str, str] = {
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "google": "Google",
    "deepseek": "DeepSeek",
    "qwen": "Qwen",
    "moonshotai": "Moonshot",
    "x-ai": "xAI",
    "minimax": "MiniMax",
    "z-ai": "Z.AI",
    "xiaomi": "Xiaomi",
    "nvidia": "NVIDIA",
    "mistralai": "Mistral",
}

# model-id slugs to skip entirely (free/experimental noise)
SKIP_SUFFIXES = (":free", ":nitro", ":extended", "-preview-free")

# A real model id/slug: alnum start, then alnum plus . _ : / - only. This is the
# guard that stops garbage from being written into config.py — the regexes that
# scrape the upstream sources use ``[^"]+`` which happily spans newlines and
# prose (an upstream error string once landed verbatim as a "model id" and broke
# the file). Anything with whitespace, quotes, '#', etc. is rejected here.
_SAFE_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")


def _is_safe_id(model_id: str) -> bool:
    return bool(_SAFE_MODEL_ID.match(model_id))


def _label(model_id: str) -> str:
    """Best-effort human label from a model slug."""
    # Known overrides
    overrides = {
        "claude-opus-4.7": "Claude Opus 4.7",
        "claude-opus-4.6": "Claude Opus 4.6",
        "claude-sonnet-4.6": "Claude Sonnet 4.6",
        "claude-sonnet-4-5": "Claude Sonnet 4.5",
        "claude-haiku-4-5": "Claude Haiku 4.5",
        "claude-haiku-4.5": "Claude Haiku 4.5",
    }
    if model_id in overrides:
        return overrides[model_id]

    # Generic: title-case each hyphen-segment, treat version numbers as-is
    parts = re.split(r"[-_]", model_id)
    out = []
    for p in parts:
        if re.fullmatch(r"[\d.]+", p):  # version number — keep as-is
            out.append(p)
        elif p.upper() in {"GPT", "GLM", "XAI", "MCP", "API"}:
            out.append(p.upper())
        else:
            out.append(p.capitalize())
    # Re-join: if starts with "Gpt", fix to "GPT-x.x …"
    label = " ".join(out)
    label = re.sub(r"\bGpt\b", "GPT", label)
    return label


def _load_openrouter_models() -> list[tuple[str, str]]:
    """Returns list of (full_id, description) from OPENROUTER_MODELS.

    Upstream layout (v2026.9.7+): ids are bare strings in
    ``for mid in (...)`` with optional text in ``_OPENROUTER_DESCRIPTIONS``.
    Older layout: list of ``("id", "desc")`` pairs in models.py.
    """
    src_path = AGENT_MODELS_CATALOG if AGENT_MODELS_CATALOG.is_file() else AGENT_MODELS
    src = src_path.read_text(encoding="utf-8")

    descs: dict[str, str] = {}
    dm = re.search(
        r"_OPENROUTER_DESCRIPTIONS\s*=\s*\{(.*?)\n\}",
        src,
        re.DOTALL,
    )
    if dm:
        descs = dict(re.findall(r'"([^"]+)"\s*:\s*"([^"]*)"', dm.group(1)))

    pairs: list[tuple[str, str]] = []

    # New form: OPENROUTER_MODELS = [ (mid, …) for mid in ( "id", … ) ]
    assign = re.search(r"OPENROUTER_MODELS\s*(?::[^\n]+)?\s*=\s*\[", src)
    if assign:
        tail = src[assign.end() :]
        # Stop before the next top-level assignment so we don't grab Vercel/etc.
        next_assign = re.search(r"\n[A-Z_][A-Z0-9_]*\s*(?::[^\n]+)?\s*=", tail)
        region = tail[: next_assign.start()] if next_assign else tail
        mid_m = re.search(r"for mid in\s*\(", region)
        if mid_m:
            start_i = mid_m.end()
            depth = 1
            j = start_i
            while j < len(region) and depth:
                ch = region[j]
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                j += 1
            body = region[start_i : j - 1]
            raw_ids = re.findall(r'"([^"]+)"', body)
            pairs = [
                (
                    mid,
                    descs.get(mid, "free" if mid.endswith(":free") else ""),
                )
                for mid in raw_ids
            ]

    if not pairs:
        # Legacy form: explicit ("id", "desc") tuples
        m = re.search(
            r"OPENROUTER_MODELS\s*(?::[^\n]+)?\s*=\s*\[(.*?)\n\]",
            src,
            re.DOTALL,
        )
        if not m:
            print(
                f"[patch] Warning: could not parse OPENROUTER_MODELS in "
                f"{src_path.relative_to(ROOT)} — skipping fallback sync"
            )
            return []
        pairs = re.findall(r'\(\s*"([^"]+)"\s*,\s*"([^"]*)"\s*\)', m.group(1))

    safe = [(mid, desc) for mid, desc in pairs if _is_safe_id(mid)]
    if len(safe) != len(pairs):
        rejected = [mid for mid, _ in pairs if not _is_safe_id(mid)]
        print(f"[patch] Warning: dropped {len(rejected)} malformed OpenRouter id(s): {rejected!r}")
    return safe

def _load_codex_models() -> list[str]:
    """Parse DEFAULT_CODEX_MODELS list literals only — never comment prose.

    Comments inside the list historically contained quoted provider names
    (e.g. ``"openai"`` in "stays out of the openai catalog"); a naive
    ``"…"`` scrape treated those as model ids and wrote bogus picker rows.
    """
    src = AGENT_CODEX.read_text(encoding="utf-8")
    m = re.search(
        r"DEFAULT_CODEX_MODELS\s*:\s*List\[str\]\s*=\s*\[(.*?)\]",
        src,
        re.DOTALL,
    )
    if not m:
        print("[patch] Warning: could not parse DEFAULT_CODEX_MODELS — skipping codex sync")
        return []
    # Drop full-line and trailing comments before extracting strings.
    body = re.sub(r"#.*?$", "", m.group(1), flags=re.MULTILINE)
    raw = re.findall(r'"([^"]+)"', body)
    # Codex slugs are versioned (digit required). Bare words like "openai" are
    # comment residue if comment-stripping ever misses a quote pair.
    safe = [mid for mid in raw if _is_safe_id(mid) and re.search(r"\d", mid)]
    if len(safe) != len(raw):
        rejected = [mid for mid in raw if mid not in safe]
        print(f"[patch] Warning: dropped {len(rejected)} non-model Codex id(s): {rejected!r}")
    return safe


def _patch_fallback_models(text: str, openrouter: list[tuple[str, str]]) -> str:
    """Insert missing entries into _FALLBACK_MODELS, grouped by provider."""
    for full_id, _desc in openrouter:
        if any(full_id.endswith(s) for s in SKIP_SUFFIXES):
            continue
        if "/" not in full_id:
            continue
        prefix, model_id = full_id.split("/", 1)
        provider_name = PROVIDER_MAP.get(prefix)
        if not provider_name:
            continue

        # Already present?
        if f'"id": "{full_id}"' in text:
            continue

        lbl = _label(model_id)
        new_entry = f'    {{"provider": "{provider_name}", "id": "{full_id}", "label": "{lbl}"}},'

        # Insert before the first existing entry for the same provider
        anchor = re.compile(rf'"provider":\s*"{re.escape(provider_name)}"')
        if anchor.search(text):
            lines = text.splitlines(keepends=True)
            for i, line in enumerate(lines):
                if anchor.search(line):
                    lines.insert(i, new_entry + "\n")
                    text = "".join(lines)
                    break
        else:
            # Provider not in fallback list yet — skip (keep list curated)
            pass

    return text


def _patch_provider_block(text: str, block_key: str, models: list[str]) -> str:
    """Insert missing model entries at the top of a _PROVIDER_MODELS[block_key] list.

    Also drops the phantom ``{"id": "openai", …}`` rows left by older scrapes
    that captured comment prose in ``codex_models.py``.
    """
    block_re = re.compile(
        rf'("{re.escape(block_key)}":\s*\[)(.*?)(\s*\],)',
        re.DOTALL,
    )

    def replacer(m: re.Match) -> str:
        body = m.group(2)
        # Remove phantom provider-name ids that earlier scrapes injected from
        # comment text in codex_models.py.
        body = re.sub(
            r"\n\s*\{\s*\"id\"\s*:\s*\"openai\"\s*,\s*\"label\"\s*:\s*\"[^\"]*\"\s*\},?",
            "",
            body,
        )
        for model_id in models:
            if model_id in body:
                continue
            lbl = _label(model_id)
            first = re.search(r"\n\s*\{", body)
            if first:
                body = (
                    body[: first.start()]
                    + f'\n        {{"id": "{model_id}", "label": "{lbl}"}},'
                    + body[first.start() :]
                )
        return m.group(1) + body + m.group(3)

    return block_re.sub(replacer, text, count=1)


def main() -> None:
    required = [AGENT_CODEX, WEBUI_CONFIG]
    if not AGENT_MODELS_CATALOG.is_file() and not AGENT_MODELS.is_file():
        sys.exit(f"[patch] Not found: {AGENT_MODELS_CATALOG} or {AGENT_MODELS}")
    for p in required:
        if not p.exists():
            sys.exit(f"[patch] Not found: {p}")

    openrouter = _load_openrouter_models()
    codex = _load_codex_models()

    print(f"[patch] OpenRouter models: {len(openrouter)}")
    print(f"[patch] Codex models: {codex}")

    # Exit 0 with "already up to date" after parsing nothing used to mask
    # upstream table renames (models.py → models_catalog_static.py). Fail
    # closed so a no-op parse cannot ship as a successful vendor patch.
    if not openrouter:
        sys.exit(
            "[patch] OpenRouter model list is empty — upstream table missing "
            "or unparseable; refusing to continue"
        )
    if not codex:
        sys.exit(
            "[patch] Codex model list is empty — DEFAULT_CODEX_MODELS missing "
            "or unparseable; refusing to continue"
        )

    original = WEBUI_CONFIG.read_text(encoding="utf-8")
    text = original

    text = _patch_fallback_models(text, openrouter)
    text = _patch_provider_block(text, "openai", codex)
    text = _patch_provider_block(text, "openai-codex", codex)

    if text == original:
        print("[patch] webui config already up to date.")
        return

    # Never write a file we just broke. Parse the result and bail (leaving the
    # original intact) if anything we inserted is not valid Python.
    try:
        compile(text, str(WEBUI_CONFIG), "exec")
    except SyntaxError as exc:
        sys.exit(
            f"[patch] refusing to write {WEBUI_CONFIG.relative_to(ROOT)}: "
            f"result does not parse ({exc})"
        )

    WEBUI_CONFIG.write_text(text, encoding="utf-8")
    print(f"[patch] Updated {WEBUI_CONFIG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
