"""WebUI proxy helpers for all-in-one (control-plane edge, no vendor patches).

Browsers on /login/ resolve relative fetch('api/auth/login') to /login/api/auth/login.
We canonicalize trailing-slash login URLs and rewrite those mistaken paths upstream.
"""
from __future__ import annotations


def _upstream_path(path: str) -> str:
    return "/" + path.lstrip("/")


def login_trailing_slash_redirect_location(path: str, query: str) -> str | None:
    """Return a 301 Location path (+ query) for /login/ URLs, or None."""
    upstream = _upstream_path(path)
    if not upstream.endswith("/login/"):
        return None
    location = upstream.rstrip("/")
    if query:
        location += "?" + query
    return location


def normalize_upstream_path(path: str) -> str:
    """Map browser mis-resolved login-relative URLs to real WebUI routes."""
    upstream = _upstream_path(path)
    if upstream.startswith("/login/api/"):
        return "/api/" + upstream[len("/login/api/") :].lstrip("/")
    if upstream == "/login/health":
        return "/health"
    return upstream
