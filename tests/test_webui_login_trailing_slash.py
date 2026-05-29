"""Regression: /login/ must not break browser password login.

Fixed at the control-plane proxy (no vendor/hermes-webui patches).
"""
from __future__ import annotations

import urllib.parse as _urlparse

from control_plane.webui_proxy import (
    login_trailing_slash_redirect_location,
    normalize_upstream_path,
)


def test_redirect_login_trailing_slash():
    assert login_trailing_slash_redirect_location("login/", "") == "/login"
    assert login_trailing_slash_redirect_location("login/", "next=%2F") == "/login?next=%2F"
    assert login_trailing_slash_redirect_location("login", "") is None
    assert login_trailing_slash_redirect_location("api/auth/login", "") is None


def test_rewrite_login_api_paths():
    assert normalize_upstream_path("login/api/auth/login") == "/api/auth/login"
    assert normalize_upstream_path("login/api/auth/status") == "/api/auth/status"


def test_rewrite_login_health_probe():
    assert normalize_upstream_path("login/health") == "/health"


def test_normal_paths_unchanged():
    assert normalize_upstream_path("login") == "/login"
    assert normalize_upstream_path("api/auth/login") == "/api/auth/login"


def test_relative_login_fetch_from_trailing_slash_is_wrong():
    bad = _urlparse.urljoin("http://127.0.0.1:8787/login/", "api/auth/login")
    assert bad.endswith("/login/api/auth/login")


def test_api_url_helper_from_login_page_is_correct():
    good = _urlparse.urljoin("http://127.0.0.1:8787/login?next=/", "api/auth/login")
    assert good == "http://127.0.0.1:8787/api/auth/login"
