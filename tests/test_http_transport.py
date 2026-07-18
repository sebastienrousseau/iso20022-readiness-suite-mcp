# Copyright (C) 2023-2026 Sebastien Rousseau.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""HTTP transport: bind parsing, bearer auth, app assembly, and run_http."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from iso20022_readiness_suite_mcp.http import oauth as oauth_mod
from iso20022_readiness_suite_mcp.http import transport
from iso20022_readiness_suite_mcp.http.context import (
    current_tenant,
)


class RecordingApp:
    """A minimal inner ASGI app that records the observed tenant context."""

    def __init__(self) -> None:
        """Start with no observed call."""
        self.called = False
        self.tenant: str | None = None

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        """Record that it ran and, for HTTP, the current tenant."""
        self.called = True
        if scope["type"] == "http":
            self.tenant = current_tenant()
            from starlette.responses import JSONResponse

            await JSONResponse({"tenant": self.tenant or ""})(
                scope, receive, send
            )


class FakeMCP:
    """Stands in for a FastMCP server, yielding a sentinel inner ASGI app."""

    def __init__(self) -> None:
        """Create the sentinel inner app returned by the builder."""
        self.inner = RecordingApp()

    def streamable_http_app(self) -> RecordingApp:
        """Return the sentinel inner ASGI app."""
        return self.inner


# --- parse_bind ------------------------------------------------------------


def test_parse_bind_valid() -> None:
    """A well-formed ``HOST:PORT`` yields the split host and int port."""
    assert transport.parse_bind("0.0.0.0:8080") == ("0.0.0.0", 8080)


def test_parse_bind_no_colon() -> None:
    """A bind without a colon is rejected."""
    with pytest.raises(ValueError, match="HOST:PORT"):
        transport.parse_bind("localhost")


def test_parse_bind_empty_host() -> None:
    """A bind with an empty host is rejected."""
    with pytest.raises(ValueError, match="HOST:PORT"):
        transport.parse_bind(":8080")


def test_parse_bind_non_int_port() -> None:
    """A non-integer port is rejected."""
    with pytest.raises(ValueError, match="must be an integer"):
        transport.parse_bind("host:abc")


def test_parse_bind_out_of_range_port() -> None:
    """A port outside 0..65535 is rejected."""
    with pytest.raises(ValueError, match="0..65535"):
        transport.parse_bind("host:70000")


# --- BearerTokenMiddleware -------------------------------------------------


async def _get(app: Any, headers: dict[str, str] | None = None) -> Any:
    """Issue an authenticated GET through an in-process ASGI transport."""
    transport_ = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport_, base_url="http://testserver"
    ) as client:
        return await client.get("/mcp", headers=headers or {})


@pytest.mark.asyncio
async def test_bearer_missing_header() -> None:
    """A request with no Authorization header is rejected 401."""
    inner = RecordingApp()
    app = transport.BearerTokenMiddleware(inner, "s3cret")
    response = await _get(app)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert inner.called is False


@pytest.mark.asyncio
async def test_bearer_wrong_token() -> None:
    """A request with the wrong bearer token is rejected 401."""
    inner = RecordingApp()
    app = transport.BearerTokenMiddleware(inner, "s3cret")
    response = await _get(app, {"Authorization": "Bearer nope"})
    assert response.status_code == 401
    assert inner.called is False


@pytest.mark.asyncio
async def test_bearer_correct_token_forwards_tenant() -> None:
    """The correct token is accepted and the tenant is forwarded."""
    inner = RecordingApp()
    app = transport.BearerTokenMiddleware(inner, "s3cret")
    response = await _get(
        app,
        {"Authorization": "Bearer s3cret", "X-MCP-Tenant": "acme"},
    )
    assert response.status_code == 200
    assert response.json() == {"tenant": "acme"}
    assert inner.tenant == "acme"


@pytest.mark.asyncio
async def test_bearer_non_http_scope_passthrough() -> None:
    """Non-HTTP scopes (e.g. lifespan) bypass auth entirely."""
    inner = RecordingApp()
    app = transport.BearerTokenMiddleware(inner, "s3cret")
    sent: list[Any] = []

    async def receive() -> dict[str, str]:
        """Yield a single lifespan startup event."""
        return {"type": "lifespan.startup"}

    async def send(message: Any) -> None:
        """Record any outbound ASGI message."""
        sent.append(message)

    await app({"type": "lifespan"}, receive, send)
    assert inner.called is True


# --- build_http_app --------------------------------------------------------


def test_build_http_app_static_token() -> None:
    """A static token yields a :class:`BearerTokenMiddleware`."""
    app = transport.build_http_app(FakeMCP(), token="s3cret")
    assert isinstance(app, transport.BearerTokenMiddleware)


def test_build_http_app_oauth() -> None:
    """An OAuth config yields an :class:`OAuthResourceMiddleware`."""
    config = oauth_mod.OAuthConfig(
        issuer="https://issuer.example.com",
        audience="https://mcp.example.com/mcp",
        jwks_url="https://issuer.example.com/.well-known/jwks.json",
    )
    app = transport.build_http_app(FakeMCP(), oauth_config=config)
    assert isinstance(app, oauth_mod.OAuthResourceMiddleware)


def test_build_http_app_requires_auth() -> None:
    """Building with neither token nor OAuth config is refused."""
    with pytest.raises(ValueError, match="static token or an OAuth config"):
        transport.build_http_app(FakeMCP())


# --- run_http --------------------------------------------------------------


@pytest.fixture
def uvicorn_recorder(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Replace ``uvicorn.run`` with a recorder capturing its arguments."""
    calls: list[dict[str, Any]] = []

    def _run(app: Any, **kwargs: Any) -> None:
        """Record the app and keyword arguments instead of serving."""
        calls.append({"app": app, **kwargs})

    monkeypatch.setattr(transport.uvicorn, "run", _run)
    return calls


def _patch_from_env(
    monkeypatch: pytest.MonkeyPatch, config: oauth_mod.OAuthConfig | None
) -> None:
    """Force ``OAuthConfig.from_env`` to return ``config``."""
    monkeypatch.setattr(
        transport._oauth.OAuthConfig,
        "from_env",
        lambda *a, **k: config,
    )


def test_run_http_oauth_wins_over_token(
    monkeypatch: pytest.MonkeyPatch,
    uvicorn_recorder: list[dict[str, Any]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """OAuth config builds the OAuth app and warns when a token co-exists."""
    config = oauth_mod.OAuthConfig(
        issuer="https://issuer.example.com",
        audience="https://mcp.example.com/mcp",
        jwks_url="https://issuer.example.com/.well-known/jwks.json",
    )
    _patch_from_env(monkeypatch, config)
    with caplog.at_level("WARNING"):
        transport.run_http(FakeMCP(), "127.0.0.1:9000", token="also-set")
    assert len(uvicorn_recorder) == 1
    assert isinstance(
        uvicorn_recorder[0]["app"], oauth_mod.OAuthResourceMiddleware
    )
    assert uvicorn_recorder[0]["host"] == "127.0.0.1"
    assert uvicorn_recorder[0]["port"] == 9000
    assert "OAuth" in caplog.text and "IGNORED" in caplog.text


def test_run_http_oauth_without_token(
    monkeypatch: pytest.MonkeyPatch,
    uvicorn_recorder: list[dict[str, Any]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """OAuth alone (no static token) builds the OAuth app without warning."""
    config = oauth_mod.OAuthConfig(
        issuer="https://issuer.example.com",
        audience="https://mcp.example.com/mcp",
        jwks_url="https://issuer.example.com/.well-known/jwks.json",
    )
    _patch_from_env(monkeypatch, config)
    monkeypatch.delenv(transport.TOKEN_ENV, raising=False)
    with caplog.at_level("WARNING"):
        transport.run_http(FakeMCP(), "127.0.0.1:9000")
    assert isinstance(
        uvicorn_recorder[0]["app"], oauth_mod.OAuthResourceMiddleware
    )
    assert "IGNORED" not in caplog.text


def test_run_http_static_token_dev_mode(
    monkeypatch: pytest.MonkeyPatch,
    uvicorn_recorder: list[dict[str, Any]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A static token (no OAuth) builds the bearer app with a dev warning."""
    _patch_from_env(monkeypatch, None)
    monkeypatch.setenv(transport.TOKEN_ENV, "env-secret")
    with caplog.at_level("WARNING"):
        transport.run_http(FakeMCP(), "0.0.0.0:8080")
    assert isinstance(
        uvicorn_recorder[0]["app"], transport.BearerTokenMiddleware
    )
    assert "DEV-MODE" in caplog.text


def test_run_http_no_auth_exits(
    monkeypatch: pytest.MonkeyPatch,
    uvicorn_recorder: list[dict[str, Any]],
) -> None:
    """Starting HTTP with neither OAuth nor a token is refused."""
    _patch_from_env(monkeypatch, None)
    monkeypatch.delenv(transport.TOKEN_ENV, raising=False)
    with pytest.raises(SystemExit, match="requires auth"):
        transport.run_http(FakeMCP(), "0.0.0.0:8080")
    assert uvicorn_recorder == []


def test_run_http_malformed_bind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed bind is rejected before any auth resolution."""
    with pytest.raises(ValueError, match="HOST:PORT"):
        transport.run_http(FakeMCP(), "bad-bind")
