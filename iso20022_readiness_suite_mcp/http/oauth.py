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

"""OAuth 2.1 resource-server auth for the HTTP transport (RFC 9728).

The HTTP transport's original credential -- a single static bearer token
compared byte-for-byte (``ISO20022_READINESS_TOKEN``) -- remains available as
an explicit **dev-mode fallback**, but production deployments should point the
server at an OAuth 2.1 authorization server instead::

    ISO20022_READINESS_OAUTH_ISSUER=https://auth.example.com \\
    ISO20022_READINESS_OAUTH_AUDIENCE=https://mcp.example.com/mcp \\
    iso20022-readiness-suite-mcp --transport=http --bind=0.0.0.0:8080

Three pieces live here: :class:`OAuthConfig` (resource-server configuration
read from ``ISO20022_READINESS_OAUTH_*``), :class:`JWTVerifier` (validates
``Authorization: Bearer`` JWTs against the JWKS, ``iss`` / ``aud`` / ``exp`` /
``nbf`` and any required scopes; implements the MCP SDK's ``TokenVerifier``
protocol), and :class:`OAuthResourceMiddleware` (the ASGI wrapper enforcing
the above, rejecting failures ``401`` / ``403`` with an RFC 9728
``WWW-Authenticate`` challenge and serving the protected-resource metadata).

The authenticated token's scopes are forwarded into the request context
(:data:`~iso20022_readiness_suite_mcp.http.context._scopes_var`) so tools can
gate premium behaviour on an entitlement scope.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
import jwt
from mcp.server.auth.provider import AccessToken
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from iso20022_readiness_suite_mcp.http.context import (
    TENANT_HEADER,
    _scopes_var,
    _tenant_var,
)

__all__ = [
    "OAUTH_AUDIENCE_ENV",
    "OAUTH_ISSUER_ENV",
    "OAUTH_JWKS_URL_ENV",
    "OAUTH_SCOPES_ENV",
    "WELL_KNOWN_PATH",
    "JWKSCache",
    "JWTVerifier",
    "OAuthConfig",
    "OAuthResourceMiddleware",
    "TokenValidationError",
    "protected_resource_metadata",
    "resource_metadata_url",
]

#: Environment variable naming the OAuth 2.1 authorization server (the JWT
#: ``iss`` claim must match it exactly).
OAUTH_ISSUER_ENV = "ISO20022_READINESS_OAUTH_ISSUER"

#: Environment variable naming this resource server's canonical resource URI
#: (RFC 8707); the JWT ``aud`` claim must contain it.
OAUTH_AUDIENCE_ENV = "ISO20022_READINESS_OAUTH_AUDIENCE"

#: Environment variable overriding the JWKS document URL. When unset,
#: ``<issuer>/.well-known/jwks.json`` is used.
OAUTH_JWKS_URL_ENV = "ISO20022_READINESS_OAUTH_JWKS_URL"

#: Environment variable listing space-separated scopes every token must carry
#: (e.g. ``"readiness:read"``). Unset / empty: no scope gate.
OAUTH_SCOPES_ENV = "ISO20022_READINESS_OAUTH_SCOPES"

#: The RFC 9728 §3 well-known path for protected-resource metadata.
WELL_KNOWN_PATH = "/.well-known/oauth-protected-resource"

#: Clock-skew tolerance (seconds) applied to ``exp`` / ``nbf`` checks.
CLOCK_SKEW_LEEWAY_S = 30

#: How long (seconds) fetched JWKS keys are served from cache before the JWKS
#: URL is consulted again. An unknown ``kid`` always triggers one refresh.
JWKS_CACHE_TTL_S = 300.0

_logger = logging.getLogger(__name__)


class TokenValidationError(Exception):
    """A bearer JWT failed validation.

    Attributes:
        reason: A short stable failure code (e.g. ``"token_expired"``) used
            for the RFC 6750 challenge and diagnostics.
        description: A human-readable detail string, safe to return to the
            caller (never echoes the token).
    """

    def __init__(self, reason: str, description: str) -> None:
        """Record the failure ``reason`` code and ``description``."""
        super().__init__(f"{reason}: {description}")
        self.reason = reason
        self.description = description


@dataclass(frozen=True)
class OAuthConfig:
    """Resource-server configuration for OAuth 2.1 JWT validation.

    Attributes:
        issuer: The authorization server's issuer identifier; the JWT ``iss``
            claim must match it exactly.
        audience: This server's canonical resource URI (RFC 8707); the JWT
            ``aud`` claim must contain it, echoed as ``resource`` in metadata.
        jwks_url: Where to fetch the JSON Web Key Set for signature checks.
        required_scopes: Scopes every token must carry; empty means no gate.
    """

    issuer: str
    audience: str
    jwks_url: str
    required_scopes: tuple[str, ...] = ()

    @classmethod
    def from_env(
        cls, environ: Mapping[str, str] | None = None
    ) -> OAuthConfig | None:
        """Read the OAuth configuration from the environment.

        Returns ``None`` when no ``ISO20022_READINESS_OAUTH_*`` variable is
        set (the caller then falls back to the static dev-mode token).

        Raises:
            SystemExit: If the configuration is partial (some variables set
                but ``ISSUER`` or ``AUDIENCE`` missing), so a typo'd
                deployment fails loudly instead of serving with weaker auth.
        """
        env = os.environ if environ is None else environ
        issuer = env.get(OAUTH_ISSUER_ENV, "").strip()
        audience = env.get(OAUTH_AUDIENCE_ENV, "").strip()
        jwks_url = env.get(OAUTH_JWKS_URL_ENV, "").strip()
        scopes = tuple(env.get(OAUTH_SCOPES_ENV, "").split())
        if not (issuer or audience or jwks_url or scopes):
            return None
        if not issuer or not audience:
            raise SystemExit(
                "Partial OAuth configuration: set both "
                f"{OAUTH_ISSUER_ENV} and {OAUTH_AUDIENCE_ENV} (with optional "
                f"{OAUTH_JWKS_URL_ENV} / {OAUTH_SCOPES_ENV}), or unset all "
                "ISO20022_READINESS_OAUTH_* variables to use the static "
                "dev-mode token."
            )
        if not jwks_url:
            jwks_url = issuer.rstrip("/") + "/.well-known/jwks.json"
        return cls(
            issuer=issuer,
            audience=audience,
            jwks_url=jwks_url,
            required_scopes=scopes,
        )


def resource_metadata_url(audience: str) -> str:
    """Build the RFC 9728 §3.1 metadata URL for a resource identifier.

    Inserts ``/.well-known/oauth-protected-resource`` between host and
    resource path, keeping the operator's string un-normalised (RFC 8707
    resource identifiers are compared as exact strings).
    """
    parsed = urlparse(audience)
    path = "" if parsed.path in ("", "/") else parsed.path
    return f"{parsed.scheme}://{parsed.netloc}{WELL_KNOWN_PATH}{path}"


def protected_resource_metadata(config: OAuthConfig) -> dict[str, Any]:
    """Build the RFC 9728 §2 protected-resource metadata document."""
    metadata: dict[str, Any] = {
        "resource": config.audience,
        "authorization_servers": [config.issuer],
        "bearer_methods_supported": ["header"],
    }
    if config.required_scopes:
        metadata["scopes_supported"] = list(config.required_scopes)
    return metadata


class JWKSCache:
    """A TTL cache of JWKS signing keys, fetched with ``httpx``.

    Keys are indexed by ``kid`` and refreshed from the JWKS URL when the cache
    is older than the TTL or when an unknown ``kid`` shows up (key rotation).
    Fetching is async; concurrent refreshes are benign (the fetch is
    idempotent), so no lock is taken.
    """

    def __init__(
        self, url: str, ttl_seconds: float = JWKS_CACHE_TTL_S
    ) -> None:
        """Create a cache reading from ``url`` with a ``ttl_seconds`` TTL."""
        self._url = url
        self._ttl = ttl_seconds
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at = float("-inf")

    def _stale(self) -> bool:
        """Return whether the cached keys are older than the TTL."""
        return time.monotonic() - self._fetched_at >= self._ttl

    async def _refresh(self) -> None:
        """Re-fetch the JWKS document and rebuild the key index.

        Raises:
            TokenValidationError: ``jwks_unavailable`` when the JWKS URL
                cannot be fetched or does not parse as a key set.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self._url)
                response.raise_for_status()
                document = response.json()
            entries = document["keys"]
            if not isinstance(entries, list):
                raise TypeError("JWKS 'keys' member is not a list")
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise TokenValidationError(
                "jwks_unavailable",
                f"could not fetch JWKS from {self._url}: "
                f"{exc.__class__.__name__}",
            ) from exc
        keys: dict[str, jwt.PyJWK] = {}
        for entry in entries:
            kid = entry.get("kid") if isinstance(entry, dict) else None
            if not kid:
                continue
            try:
                keys[kid] = jwt.PyJWK(entry)
            except (
                jwt.exceptions.PyJWKError,
                jwt.exceptions.InvalidKeyError,
            ):
                continue  # skip unusable entries, keep the good ones
        self._keys = keys
        self._fetched_at = time.monotonic()

    async def get_key(self, kid: str | None) -> jwt.PyJWK:
        """Resolve the signing key for ``kid``.

        ``kid`` may be ``None`` only when the key set holds exactly one key.

        Raises:
            TokenValidationError: ``jwks_unavailable`` on fetch failure,
                ``unknown_kid`` when no key matches, ``missing_kid`` when the
                token names no key and the set is ambiguous.
        """
        if self._stale() or (kid is not None and kid not in self._keys):
            await self._refresh()
        if kid is None:
            if len(self._keys) == 1:
                return next(iter(self._keys.values()))
            raise TokenValidationError(
                "missing_kid",
                "token header has no 'kid' and the JWKS is ambiguous",
            )
        try:
            return self._keys[kid]
        except KeyError:
            raise TokenValidationError(
                "unknown_kid", f"no JWKS key matches kid {kid!r}"
            ) from None


#: Maps PyJWT validation exceptions to stable failure-reason codes. Order
#: matters: subclasses must precede their bases.
_JWT_ERROR_REASONS: tuple[tuple[type[Exception], str], ...] = (
    (jwt.exceptions.ExpiredSignatureError, "token_expired"),
    (jwt.exceptions.ImmatureSignatureError, "token_not_yet_valid"),
    (jwt.exceptions.InvalidIssuerError, "issuer_mismatch"),
    (jwt.exceptions.InvalidAudienceError, "audience_mismatch"),
    (jwt.exceptions.InvalidSignatureError, "signature_invalid"),
    (jwt.exceptions.MissingRequiredClaimError, "missing_required_claim"),
)


class JWTVerifier:
    """Validates OAuth 2.1 bearer JWTs against the resource config.

    Implements the MCP SDK's ``TokenVerifier`` protocol (:meth:`verify_token`)
    on top of :meth:`verify`, which raises a reason-coded
    :class:`TokenValidationError`. Algorithm confusion is prevented
    structurally: the verification algorithm is always taken from the JWKS key
    (``PyJWK.algorithm_name``), never from the attacker-controlled token
    header, so ``none`` / HMAC downgrades are impossible with an asymmetric
    key set.
    """

    def __init__(
        self, config: OAuthConfig, jwks: JWKSCache | None = None
    ) -> None:
        """Create a verifier for ``config`` (building a JWKS cache if none)."""
        self._config = config
        self._jwks = jwks if jwks is not None else JWKSCache(config.jwks_url)

    async def verify(self, token: str) -> AccessToken:
        """Validate ``token`` fully, raising on any failure.

        Checks, in order: structure, signing-key resolution (JWKS),
        signature, ``exp`` / ``nbf`` (with :data:`CLOCK_SKEW_LEEWAY_S`),
        ``iss``, ``aud``, and the configured required scopes.

        Raises:
            TokenValidationError: With a stable ``reason`` code on failure.
        """
        try:
            header = jwt.get_unverified_header(token)
        except jwt.exceptions.InvalidTokenError as exc:
            raise TokenValidationError(
                "malformed_token", f"not a decodable JWT: {exc}"
            ) from exc
        key = await self._jwks.get_key(header.get("kid"))
        try:
            claims = jwt.decode(
                token,
                key=key.key,
                algorithms=[key.algorithm_name],
                audience=self._config.audience,
                issuer=self._config.issuer,
                leeway=CLOCK_SKEW_LEEWAY_S,
                options={"require": ["exp", "iss", "aud"]},
            )
        except jwt.exceptions.InvalidTokenError as exc:
            for exc_type, reason in _JWT_ERROR_REASONS:
                if isinstance(exc, exc_type):
                    raise TokenValidationError(reason, str(exc)) from exc
            raise TokenValidationError("invalid_token", str(exc)) from exc
        scopes = str(claims.get("scope", "")).split()
        missing = [
            scope
            for scope in self._config.required_scopes
            if scope not in scopes
        ]
        if missing:
            raise TokenValidationError(
                "insufficient_scope",
                "token lacks required scope(s): " + " ".join(missing),
            )
        client_id = str(
            claims.get("client_id")
            or claims.get("azp")
            or claims.get("sub")
            or ""
        )
        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=scopes,
            expires_at=claims.get("exp"),
            resource=self._config.audience,
            subject=claims.get("sub"),
            claims=claims,
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        """SDK ``TokenVerifier`` protocol adapter over :meth:`verify`."""
        try:
            return await self.verify(token)
        except TokenValidationError:
            return None


class OAuthResourceMiddleware:
    """ASGI middleware enforcing OAuth 2.1 JWT auth per RFC 9728.

    Every HTTP request must carry ``Authorization: Bearer <jwt>`` passing
    :class:`JWTVerifier`; failures are rejected ``401`` (``403`` for
    ``insufficient_scope``) with a ``WWW-Authenticate`` challenge carrying the
    ``resource_metadata`` URL (RFC 9728 §5.1). The metadata document itself is
    served unauthenticated on ``GET`` to :data:`WELL_KNOWN_PATH` and its
    audience-derived variant. Authorized requests forward the optional
    ``X-MCP-Tenant`` header and the token's scopes into the request context.
    """

    def __init__(
        self,
        app: ASGIApp,
        verifier: JWTVerifier,
        config: OAuthConfig,
    ) -> None:
        """Wrap ``app`` behind OAuth 2.1 auth for ``config``."""
        self._app = app
        self._verifier = verifier
        self._config = config
        self._metadata = protected_resource_metadata(config)
        self._resource_metadata_url = resource_metadata_url(config.audience)
        self._well_known_paths = {
            WELL_KNOWN_PATH,
            urlparse(self._resource_metadata_url).path,
        }

    def _challenge(self, error: str, description: str) -> str:
        """Build the RFC 6750 / RFC 9728 ``WWW-Authenticate`` value."""
        return (
            f'Bearer error="{error}", '
            f'error_description="{description}", '
            f'resource_metadata="{self._resource_metadata_url}"'
        )

    async def _reject(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        failure: TokenValidationError,
    ) -> None:
        """Send the 401/403 rejection for ``failure``."""
        insufficient = failure.reason == "insufficient_scope"
        status = 403 if insufficient else 401
        error = "insufficient_scope" if insufficient else "invalid_token"
        _logger.info(
            "http request rejected: path=%s reason=%s",
            scope.get("path", ""),
            failure.reason,
        )
        response = JSONResponse(
            {"error": error, "error_description": failure.description},
            status_code=status,
            headers={
                "WWW-Authenticate": self._challenge(error, failure.description)
            },
        )
        await response(scope, receive, send)

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Authenticate one ASGI event and dispatch it downstream."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path in self._well_known_paths and scope.get("method") in (
            "GET",
            "HEAD",
        ):
            await JSONResponse(self._metadata)(scope, receive, send)
            return
        headers = Headers(scope=scope)
        tenant = headers.get(TENANT_HEADER)
        supplied = headers.get("Authorization", "")
        auth_scheme, _, credential = supplied.partition(" ")
        if auth_scheme.lower() != "bearer" or not credential.strip():
            await self._reject(
                scope,
                receive,
                send,
                TokenValidationError(
                    "missing_bearer",
                    "expected 'Authorization: Bearer <token>'",
                ),
            )
            return
        try:
            access = await self._verifier.verify(credential.strip())
        except TokenValidationError as failure:
            await self._reject(scope, receive, send, failure)
            return
        tenant_token = _tenant_var.set(tenant)
        scopes_token = _scopes_var.set(tuple(access.scopes))
        try:
            await self._app(scope, receive, send)
        finally:
            _tenant_var.reset(tenant_token)
            _scopes_var.reset(scopes_token)
