"""Env proxy reaches the MCP HTTP/SSE transports.

``tools/mcp_tool_transport.py`` hands httpx an explicit ``transport=`` (the wire-body cap
wrapping an ``AsyncHTTPTransport``). httpx only applies ``HTTPS_PROXY`` / ``ALL_PROXY`` by
mounting proxy transports around its *default* transport, so a custom transport silently
bypasses ``trust_env`` and every MCP connection goes out direct. Deployments whose MCP
servers are only reachable through a proxy (Tailscale userspace networking, corporate
egress) lose all MCP tools with a DNS/connect error.

These cover the proxy resolution helper, NO_PROXY agreement with the rest of Hermes, and
that both transport builders put the proxy on the inner transport.
"""

import httpx
import pytest

from tools.mcp_tool_transport import _env_proxy_for

PROXY = "http://127.0.0.1:1055"
URL = "https://mcp.internal.example/mcp"


@pytest.fixture(autouse=True)
def _clean_proxy_env(monkeypatch):
    for key in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY",
                "https_proxy", "http_proxy", "all_proxy",
                "NO_PROXY", "no_proxy"):
        monkeypatch.delenv(key, raising=False)


def test_no_proxy_env_returns_none():
    assert _env_proxy_for(URL) is None


@pytest.mark.parametrize("env_key", ["HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY",
                                     "https_proxy", "http_proxy", "all_proxy"])
def test_each_proxy_env_var_is_honoured(monkeypatch, env_key):
    monkeypatch.setenv(env_key, PROXY)
    assert _env_proxy_for(URL) == PROXY


def test_no_proxy_exact_host_bypasses(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", PROXY)
    monkeypatch.setenv("NO_PROXY", "mcp.internal.example")
    assert _env_proxy_for(URL) is None


def test_no_proxy_wildcard_suffix_bypasses(monkeypatch):
    """The shared matcher understands ``*.`` forms that stdlib proxy_bypass_environment misses."""
    monkeypatch.setenv("HTTPS_PROXY", PROXY)
    monkeypatch.setenv("NO_PROXY", "*.internal.example")
    assert _env_proxy_for(URL) is None


def test_no_proxy_non_matching_host_still_proxied(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", PROXY)
    monkeypatch.setenv("NO_PROXY", "other.example")
    assert _env_proxy_for(URL) == PROXY


def test_blank_proxy_env_returns_none(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "   ")
    assert _env_proxy_for(URL) is None


def _inner_transport_of(capped):
    """Unwrap the body-cap transport to the AsyncHTTPTransport it delegates to."""
    for attr in ("_inner", "_transport", "inner"):
        inner = getattr(capped, attr, None)
        if inner is not None:
            return inner
    raise AssertionError(f"could not unwrap body-cap transport: {type(capped)!r}")


def _transport_is_proxied(transport) -> bool:
    """True when httpx built this transport against a proxy (its pool is a proxy pool)."""
    pool = getattr(transport, "_pool", None)
    return type(pool).__name__ in {"AsyncHTTPProxy", "AsyncSOCKSProxy"}


def _server():
    from tools.mcp_tool_transport import MCPServerTransportMixin

    class _Server(MCPServerTransportMixin):
        name = "probe"

    return _Server()


def _capture_body_cap_inner(monkeypatch):
    """Record the inner transport handed to the body-cap wrapper.

    Both transport builders call ``_make_mcp_body_cap_transport(httpx, inner)`` while
    assembling their client, so this sees the real object the fix configures — the httpx
    client itself is only constructed later, when the caller enters the context manager.
    """
    from tools import mcp_tool_transport as mod

    seen = []
    real = mod._make_mcp_body_cap_transport

    def _spy(httpx_mod, inner, *args, **kwargs):
        seen.append(inner)
        return real(httpx_mod, inner, *args, **kwargs)

    monkeypatch.setattr(mod, "_make_mcp_body_cap_transport", _spy)
    return seen


def _build_streamable_http_ctx():
    return _server()._streamable_http_transport(
        URL, headers={}, connect_timeout=30.0, ssl_verify=True, client_cert=None,
        oauth_auth=None, strict_cfg_headers=False, configured_header_names=set())


def test_httpx_ignores_env_proxy_when_transport_is_explicit(monkeypatch):
    """Regression guard: this is the exact httpx behaviour the fix works around.

    If a future httpx starts honouring env proxies through an explicit transport, this
    fails and _env_proxy_for can be reconsidered.
    """
    monkeypatch.setenv("HTTPS_PROXY", PROXY)
    client = httpx.AsyncClient(trust_env=True,
                               transport=httpx.AsyncHTTPTransport(verify=True))
    assert not _transport_is_proxied(client._transport)
    assert client._mounts == {}


def test_async_transport_accepts_proxy_kwarg():
    """The inner transport is proxied when built the way the fix builds it."""
    transport = httpx.AsyncHTTPTransport(verify=True, proxy=PROXY)
    assert _transport_is_proxied(transport)


@pytest.mark.parametrize("env_key", ["HTTPS_PROXY", "ALL_PROXY"])
def test_streamable_http_builds_proxied_inner_transport(monkeypatch, env_key):
    """_streamable_http_transport puts the env proxy on the inner transport."""
    monkeypatch.setenv(env_key, PROXY)
    captured = _capture_body_cap_inner(monkeypatch)

    _build_streamable_http_ctx()

    assert captured, "body-cap transport was never built"
    assert _transport_is_proxied(captured[-1])


def test_streamable_http_inner_transport_direct_without_proxy_env(monkeypatch):
    """No proxy env → the inner transport stays direct (no behaviour change)."""
    captured = _capture_body_cap_inner(monkeypatch)

    _build_streamable_http_ctx()

    assert captured, "body-cap transport was never built"
    assert not _transport_is_proxied(captured[-1])


def test_streamable_http_respects_no_proxy(monkeypatch):
    """NO_PROXY covering the MCP host keeps the inner transport direct."""
    monkeypatch.setenv("HTTPS_PROXY", PROXY)
    monkeypatch.setenv("NO_PROXY", "*.internal.example")
    captured = _capture_body_cap_inner(monkeypatch)

    _build_streamable_http_ctx()

    assert captured, "body-cap transport was never built"
    assert not _transport_is_proxied(captured[-1])


def test_sse_builds_proxied_inner_transport(monkeypatch):
    """The SSE client factory also proxies its inner transport."""
    monkeypatch.setenv("HTTPS_PROXY", PROXY)
    captured = _capture_body_cap_inner(monkeypatch)

    from tools import mcp_tool_transport as mod
    import tools.mcp_tool as mcp_tool_mod

    mod._core._ensure_mcp_sdk()
    factory = {}
    # _core is an origin-proxy view onto tools.mcp_tool; patch the module it forwards to.
    monkeypatch.setattr(mcp_tool_mod, "sse_client",
                        lambda **kw: factory.update(kw) or object(),
                        raising=False)
    _server()._sse_transport(URL, headers={}, connect_timeout=30.0,
                             ssl_verify=True, client_cert=None, oauth_auth=None,
                             strict_cfg_headers=False)

    build = factory.get("httpx_client_factory")
    assert build is not None, "sse_client got no httpx_client_factory"
    build()  # the factory builds the client (and its transport) on call

    assert captured, "body-cap transport was never built"
    assert _transport_is_proxied(captured[-1])


def test_no_proxy_env_leaves_transport_direct():
    """With no proxy configured the transport must stay direct (no behaviour change)."""
    transport = httpx.AsyncHTTPTransport(verify=True)
    assert not _transport_is_proxied(transport)
