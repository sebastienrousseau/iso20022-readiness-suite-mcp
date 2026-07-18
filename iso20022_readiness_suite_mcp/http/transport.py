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

"""HTTP transport, bearer-token auth, and tenant scoping.

The server speaks stdio by default -- launched by a local MCP client, one
process per operator, with no authentication surface. This module adds an
opt-in **streamable-HTTP** transport for shared, multi-tenant deployments::

    ISO20022_READINESS_TOKEN=s3cret \\
        iso20022-readiness-suite-mcp --transport=http --bind=0.0.0.0:8080

Two auth modes apply, strongest first: an OAuth 2.1 resource server (when the
``ISO20022_READINESS_OAUTH_*`` variables are set, see
:mod:`~iso20022_readiness_suite_mcp.http.oauth`), or a static dev-mode bearer
token compared with :func:`hmac.compare_digest`. Starting the HTTP transport
with neither is refused rather than silently serving an unauthenticated
endpoint. HTTP callers may send an optional ``X-MCP-Tenant`` header, forwarded
into the tenant context variable for the duration of the request.
"""

from __future__ import annotations

import hmac
import logging
import os
from typing import TYPE_CHECKING

import uvicorn
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from iso20022_readiness_suite_mcp.http import oauth as _oauth
from iso20022_readiness_suite_mcp.http.context import (
    TENANT_HEADER,
    _tenant_var,
)

if TYPE_CHECKING:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP

__all__ = [
    "DEFAULT_BIND",
    "TOKEN_ENV",
    "BearerTokenMiddleware",
    "build_http_app",
    "parse_bind",
    "run_http",
]

#: The environment variable the HTTP transport reads its static bearer token
#: from. The string is the variable's *name*, not a credential.
TOKEN_ENV = "ISO20022_READINESS_TOKEN"  # nosec B105

#: The default ``--bind`` for ``--transport=http``: loopback-only, so an
#: operator must opt in explicitly (e.g. ``0.0.0.0:8080``) to expose it.
DEFAULT_BIND = "127.0.0.1:8080"

_logger = logging.getLogger(__name__)


def parse_bind(bind: str) -> tuple[str, int]:
    """Parse a ``HOST:PORT`` bind string into a ``(host, port)`` pair.

    Raises:
        ValueError: If ``bind`` is not ``HOST:PORT`` with a non-empty host
            and a port in ``0..65535``.
    """
    host, sep, port_text = bind.rpartition(":")
    if not sep or not host:
        raise ValueError(
            f"--bind must be HOST:PORT (e.g. '0.0.0.0:8080'), got {bind!r}"
        )
    try:
        port = int(port_text)
    except ValueError:
        raise ValueError(
            f"--bind port must be an integer, got {port_text!r}"
        ) from None
    if not 0 <= port <= 65535:
        raise ValueError(f"--bind port must be in 0..65535, got {port}")
    return host, port


class BearerTokenMiddleware:
    """Pure ASGI middleware enforcing static ``Authorization: Bearer`` auth.

    Wraps FastMCP's streamable-HTTP Starlette app. Every HTTP request must
    present exactly ``Authorization: Bearer <token>`` (compared with
    :func:`hmac.compare_digest`); anything else is rejected ``401`` before
    reaching the MCP session manager. Authorized requests forward the optional
    ``X-MCP-Tenant`` header into the tenant context variable. Implemented as
    raw ASGI so streaming SSE responses pass through untouched.
    """

    def __init__(self, app: ASGIApp, token: str) -> None:
        """Wrap ``app``, requiring ``token`` on every HTTP request."""
        self._app = app
        self._token = token

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Authenticate one ASGI event and dispatch it downstream."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        tenant = headers.get(TENANT_HEADER)
        supplied = headers.get("Authorization", "")
        expected = f"Bearer {self._token}"
        if not hmac.compare_digest(
            supplied.encode("utf-8"), expected.encode("utf-8")
        ):
            _logger.info(
                "http request rejected: path=%s reason=invalid_static_token",
                scope.get("path", ""),
            )
            response = JSONResponse(
                {"error": "Unauthorized: missing or invalid bearer token"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        reset_token = _tenant_var.set(tenant)
        try:
            await self._app(scope, receive, send)
        finally:
            _tenant_var.reset(reset_token)


def build_http_app(
    mcp_server: FastMCP,
    token: str | None = None,
    oauth_config: _oauth.OAuthConfig | None = None,
) -> ASGIApp:
    """Build the authenticated streamable-HTTP ASGI app.

    Exactly one auth mode applies: when ``oauth_config`` is given the app
    enforces OAuth 2.1 resource-server JWT validation (RFC 9728); otherwise
    the static dev-mode ``token`` is required.

    Raises:
        ValueError: If neither ``token`` nor ``oauth_config`` is given.
    """
    inner = mcp_server.streamable_http_app()
    if oauth_config is not None:
        return _oauth.OAuthResourceMiddleware(
            inner, _oauth.JWTVerifier(oauth_config), oauth_config
        )
    if token:
        return BearerTokenMiddleware(inner, token)
    raise ValueError(
        "build_http_app requires a static token or an OAuth config"
    )


def run_http(mcp_server: FastMCP, bind: str, token: str | None = None) -> None:
    """Serve the MCP server over authenticated streamable HTTP.

    Blocks until the process is stopped. Auth is resolved from the
    environment, strongest first: OAuth 2.1 (when ``ISO20022_READINESS_OAUTH_*``
    is set) else the static :data:`TOKEN_ENV` token. Starting with neither is
    refused.

    Raises:
        SystemExit: If neither OAuth nor a static token is configured, or the
            OAuth configuration is partial.
        ValueError: If ``bind`` is malformed.
    """
    host, port = parse_bind(bind)
    oauth_config = _oauth.OAuthConfig.from_env()
    if token is None:
        token = os.environ.get(TOKEN_ENV)
    if oauth_config is not None:
        if token:
            _logger.warning(
                "Both OAuth (%s) and the static token (%s) are set; OAuth "
                "wins and the static token is IGNORED.",
                _oauth.OAUTH_ISSUER_ENV,
                TOKEN_ENV,
            )
        app = build_http_app(mcp_server, oauth_config=oauth_config)
    elif token:
        _logger.warning(
            "HTTP transport is using the static %s bearer token -- DEV-MODE "
            "auth (single shared secret, no expiry, no scopes). Configure %s "
            "/ %s for OAuth 2.1 in production.",
            TOKEN_ENV,
            _oauth.OAUTH_ISSUER_ENV,
            _oauth.OAUTH_AUDIENCE_ENV,
        )
        app = build_http_app(mcp_server, token=token)
    else:
        raise SystemExit(
            f"--transport=http requires auth: set {TOKEN_ENV} to a non-empty "
            "secret (dev mode; every HTTP request must then send "
            "'Authorization: Bearer <secret>'), or configure OAuth 2.1 via "
            f"{_oauth.OAUTH_ISSUER_ENV} and {_oauth.OAUTH_AUDIENCE_ENV}."
        )
    uvicorn.run(app, host=host, port=port, log_level="info")
