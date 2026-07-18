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

"""OAuth 2.1 resource-server auth: config, JWKS cache, verifier, middleware."""

from __future__ import annotations

import time
from typing import Any

import httpx
import jwt
import pytest

from iso20022_readiness_suite_mcp.http import oauth as oauth_mod
from iso20022_readiness_suite_mcp.http.context import (
    current_scopes,
    current_tenant,
)
from tests._jwt_helpers import (
    jwks_entry,
    make_keypair,
    pyjwk,
    sign,
)

ISS = "https://issuer.example.com"
AUD = "https://mcp.example.com/mcp"


# --- OAuthConfig.from_env --------------------------------------------------


def test_from_env_empty_returns_none() -> None:
    """No OAuth variables set yields ``None`` (fall back to static token)."""
    assert oauth_mod.OAuthConfig.from_env({}) is None


def test_from_env_partial_exits() -> None:
    """Only the issuer set (no audience) is a fatal partial config."""
    env = {oauth_mod.OAUTH_ISSUER_ENV: ISS}
    with pytest.raises(SystemExit, match="Partial OAuth configuration"):
        oauth_mod.OAuthConfig.from_env(env)


def test_from_env_defaults_jwks_url() -> None:
    """Issuer + audience default the JWKS URL under the issuer origin."""
    env = {
        oauth_mod.OAUTH_ISSUER_ENV: ISS + "/",
        oauth_mod.OAUTH_AUDIENCE_ENV: AUD,
    }
    config = oauth_mod.OAuthConfig.from_env(env)
    assert config is not None
    assert config.jwks_url == ISS + "/.well-known/jwks.json"
    assert config.required_scopes == ()


def test_from_env_explicit_jwks_and_scopes() -> None:
    """An explicit JWKS URL and scopes are honoured verbatim."""
    env = {
        oauth_mod.OAUTH_ISSUER_ENV: ISS,
        oauth_mod.OAUTH_AUDIENCE_ENV: AUD,
        oauth_mod.OAUTH_JWKS_URL_ENV: "https://keys.example.com/jwks",
        oauth_mod.OAUTH_SCOPES_ENV: "readiness:read readiness:admin",
    }
    config = oauth_mod.OAuthConfig.from_env(env)
    assert config is not None
    assert config.jwks_url == "https://keys.example.com/jwks"
    assert config.required_scopes == ("readiness:read", "readiness:admin")


# --- resource_metadata_url / protected_resource_metadata -------------------


def test_resource_metadata_url_with_path() -> None:
    """A resource identifier with a path keeps the path as a suffix."""
    assert (
        oauth_mod.resource_metadata_url("https://mcp.example.com/mcp")
        == "https://mcp.example.com/.well-known/oauth-protected-resource/mcp"
    )


def test_resource_metadata_url_bare_origin() -> None:
    """A bare-origin resource identifier gets the plain well-known path."""
    assert (
        oauth_mod.resource_metadata_url("https://mcp.example.com")
        == "https://mcp.example.com/.well-known/oauth-protected-resource"
    )
    assert (
        oauth_mod.resource_metadata_url("https://mcp.example.com/")
        == "https://mcp.example.com/.well-known/oauth-protected-resource"
    )


def test_protected_resource_metadata_without_scopes() -> None:
    """Metadata omits ``scopes_supported`` when no scopes are required."""
    config = oauth_mod.OAuthConfig(ISS, AUD, "https://x")
    metadata = oauth_mod.protected_resource_metadata(config)
    assert metadata == {
        "resource": AUD,
        "authorization_servers": [ISS],
        "bearer_methods_supported": ["header"],
    }


def test_protected_resource_metadata_with_scopes() -> None:
    """Metadata lists ``scopes_supported`` when scopes are required."""
    config = oauth_mod.OAuthConfig(ISS, AUD, "https://x", ("readiness:read",))
    metadata = oauth_mod.protected_resource_metadata(config)
    assert metadata["scopes_supported"] == ["readiness:read"]


# --- JWKSCache._refresh (real fetch, faked httpx) --------------------------


def _install_fake_httpx(
    monkeypatch: pytest.MonkeyPatch,
    *,
    payload: Any = None,
    get_exc: Exception | None = None,
    status_exc: Exception | None = None,
    json_exc: Exception | None = None,
) -> None:
    """Replace ``oauth.httpx.AsyncClient`` with a scripted fake client."""

    class _Resp:
        def raise_for_status(self) -> None:
            if status_exc is not None:
                raise status_exc

        def json(self) -> Any:
            if json_exc is not None:
                raise json_exc
            return payload

    class _Client:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *args: Any) -> bool:
            return False

        async def get(self, url: str) -> _Resp:
            if get_exc is not None:
                raise get_exc
            return _Resp()

    monkeypatch.setattr(oauth_mod.httpx, "AsyncClient", _Client)


@pytest.mark.asyncio
async def test_refresh_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """A well-formed JWKS document populates the key index."""
    key, _ = make_keypair()
    _install_fake_httpx(monkeypatch, payload={"keys": [jwks_entry(key, "k1")]})
    cache = oauth_mod.JWKSCache("https://keys.example.com/jwks")
    await cache._refresh()
    assert set(cache._keys) == {"k1"}
    assert isinstance(cache._keys["k1"], jwt.PyJWK)


@pytest.mark.asyncio
async def test_refresh_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """An HTTP failure surfaces as ``jwks_unavailable``."""
    _install_fake_httpx(monkeypatch, get_exc=httpx.HTTPError("boom"))
    cache = oauth_mod.JWKSCache("https://keys.example.com/jwks")
    with pytest.raises(oauth_mod.TokenValidationError) as info:
        await cache._refresh()
    assert info.value.reason == "jwks_unavailable"


@pytest.mark.asyncio
async def test_refresh_status_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-2xx status surfaces as ``jwks_unavailable``."""
    _install_fake_httpx(monkeypatch, status_exc=httpx.HTTPError("500"))
    cache = oauth_mod.JWKSCache("https://keys.example.com/jwks")
    with pytest.raises(oauth_mod.TokenValidationError) as info:
        await cache._refresh()
    assert info.value.reason == "jwks_unavailable"


@pytest.mark.asyncio
async def test_refresh_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """A body that is not JSON surfaces as ``jwks_unavailable``."""
    _install_fake_httpx(monkeypatch, json_exc=ValueError("not json"))
    cache = oauth_mod.JWKSCache("https://keys.example.com/jwks")
    with pytest.raises(oauth_mod.TokenValidationError) as info:
        await cache._refresh()
    assert info.value.reason == "jwks_unavailable"


@pytest.mark.asyncio
async def test_refresh_missing_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """A document without a ``keys`` member surfaces as ``jwks_unavailable``."""
    _install_fake_httpx(monkeypatch, payload={})
    cache = oauth_mod.JWKSCache("https://keys.example.com/jwks")
    with pytest.raises(oauth_mod.TokenValidationError) as info:
        await cache._refresh()
    assert info.value.reason == "jwks_unavailable"


@pytest.mark.asyncio
async def test_refresh_keys_not_a_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-list ``keys`` member surfaces as ``jwks_unavailable``."""
    _install_fake_httpx(monkeypatch, payload={"keys": "nope"})
    cache = oauth_mod.JWKSCache("https://keys.example.com/jwks")
    with pytest.raises(oauth_mod.TokenValidationError) as info:
        await cache._refresh()
    assert info.value.reason == "jwks_unavailable"


@pytest.mark.asyncio
async def test_refresh_skips_entry_without_kid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A JWKS entry with no ``kid`` is skipped, the good one retained."""
    key, _ = make_keypair()
    no_kid = {"kty": "RSA", "n": "abc", "e": "AQAB"}
    _install_fake_httpx(
        monkeypatch,
        payload={"keys": [no_kid, jwks_entry(key, "k1")]},
    )
    cache = oauth_mod.JWKSCache("https://keys.example.com/jwks")
    await cache._refresh()
    assert set(cache._keys) == {"k1"}


@pytest.mark.asyncio
async def test_refresh_skips_unusable_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A JWKS entry that fails to build a PyJWK is skipped."""
    key, _ = make_keypair()
    bad = {"kid": "bad", "kty": "RSA"}
    _install_fake_httpx(
        monkeypatch,
        payload={"keys": [bad, jwks_entry(key, "k1")]},
    )
    cache = oauth_mod.JWKSCache("https://keys.example.com/jwks")
    await cache._refresh()
    assert set(cache._keys) == {"k1"}


# --- JWKSCache.get_key -----------------------------------------------------


def _fresh_cache(keys: dict[str, jwt.PyJWK]) -> oauth_mod.JWKSCache:
    """Build a cache pre-populated with ``keys`` and marked non-stale."""
    cache = oauth_mod.JWKSCache("https://keys.example.com/jwks")
    cache._keys = keys
    cache._fetched_at = float("inf")
    return cache


@pytest.mark.asyncio
async def test_get_key_kid_cached() -> None:
    """A known ``kid`` is returned straight from the cache."""
    key, _ = make_keypair()
    entry = pyjwk(key, "k1")
    cache = _fresh_cache({"k1": entry})
    assert await cache.get_key("k1") is entry


@pytest.mark.asyncio
async def test_get_key_none_kid_single() -> None:
    """A ``None`` kid resolves to the sole key when unambiguous."""
    key, _ = make_keypair()
    entry = pyjwk(key, "k1")
    cache = _fresh_cache({"k1": entry})
    assert await cache.get_key(None) is entry


@pytest.mark.asyncio
async def test_get_key_none_kid_ambiguous() -> None:
    """A ``None`` kid with multiple keys is ``missing_kid``."""
    k1, _ = make_keypair()
    k2, _ = make_keypair()
    cache = _fresh_cache({"k1": pyjwk(k1, "k1"), "k2": pyjwk(k2, "k2")})
    with pytest.raises(oauth_mod.TokenValidationError) as info:
        await cache.get_key(None)
    assert info.value.reason == "missing_kid"


@pytest.mark.asyncio
async def test_get_key_unknown_kid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unknown ``kid`` triggers a refresh then ``unknown_kid``."""
    key, _ = make_keypair()
    cache = _fresh_cache({"k1": pyjwk(key, "k1")})

    async def _noop() -> None:
        return None

    monkeypatch.setattr(cache, "_refresh", _noop)
    with pytest.raises(oauth_mod.TokenValidationError) as info:
        await cache.get_key("k2")
    assert info.value.reason == "unknown_kid"


@pytest.mark.asyncio
async def test_get_key_stale_triggers_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale cache is refreshed before the key is resolved."""
    key, _ = make_keypair()
    entry = pyjwk(key, "k1")
    cache = oauth_mod.JWKSCache("https://keys.example.com/jwks")
    called: list[bool] = []

    async def _refresh() -> None:
        called.append(True)
        cache._keys = {"k1": entry}

    monkeypatch.setattr(cache, "_refresh", _refresh)
    assert await cache.get_key("k1") is entry
    assert called == [True]


# --- JWTVerifier.verify ----------------------------------------------------


def _make_verifier(
    key: Any, *, required_scopes: tuple[str, ...] = ()
) -> oauth_mod.JWTVerifier:
    """Build a verifier whose JWKS cache holds ``key`` under kid ``k1``."""
    config = oauth_mod.OAuthConfig(
        issuer=ISS,
        audience=AUD,
        jwks_url="https://keys.example.com/jwks",
        required_scopes=required_scopes,
    )
    cache = oauth_mod.JWKSCache("https://keys.example.com/jwks")
    cache._keys = {"k1": pyjwk(key, "k1")}
    cache._fetched_at = float("inf")
    return oauth_mod.JWTVerifier(config, jwks=cache)


@pytest.mark.asyncio
async def test_verify_valid() -> None:
    """A well-formed token yields an :class:`AccessToken`."""
    key, pem = make_keypair()
    verifier = _make_verifier(key)
    token = sign(pem, scope="readiness:read", extra={"sub": "user-1"})
    access = await verifier.verify(token)
    assert access.token == token
    assert access.scopes == ["readiness:read"]
    assert access.resource == AUD
    assert access.subject == "user-1"


@pytest.mark.asyncio
async def test_verify_expired() -> None:
    """An expired token is ``token_expired``."""
    key, pem = make_keypair()
    verifier = _make_verifier(key)
    token = sign(pem, expires_in=-3600)
    with pytest.raises(oauth_mod.TokenValidationError) as info:
        await verifier.verify(token)
    assert info.value.reason == "token_expired"


@pytest.mark.asyncio
async def test_verify_not_yet_valid() -> None:
    """A token with a future ``nbf`` is ``token_not_yet_valid``."""
    key, pem = make_keypair()
    verifier = _make_verifier(key)
    token = sign(pem, extra={"nbf": int(time.time()) + 3600})
    with pytest.raises(oauth_mod.TokenValidationError) as info:
        await verifier.verify(token)
    assert info.value.reason == "token_not_yet_valid"


@pytest.mark.asyncio
async def test_verify_issuer_mismatch() -> None:
    """A wrong issuer is ``issuer_mismatch``."""
    key, pem = make_keypair()
    verifier = _make_verifier(key)
    token = sign(pem, issuer="https://evil.example.com")
    with pytest.raises(oauth_mod.TokenValidationError) as info:
        await verifier.verify(token)
    assert info.value.reason == "issuer_mismatch"


@pytest.mark.asyncio
async def test_verify_audience_mismatch() -> None:
    """A wrong audience is ``audience_mismatch``."""
    key, pem = make_keypair()
    verifier = _make_verifier(key)
    token = sign(pem, audience="https://evil.example.com")
    with pytest.raises(oauth_mod.TokenValidationError) as info:
        await verifier.verify(token)
    assert info.value.reason == "audience_mismatch"


@pytest.mark.asyncio
async def test_verify_signature_invalid() -> None:
    """A token signed by a different key (same kid) is ``signature_invalid``."""
    key, _ = make_keypair()
    _, other_pem = make_keypair()
    verifier = _make_verifier(key)
    token = sign(other_pem, kid="k1")
    with pytest.raises(oauth_mod.TokenValidationError) as info:
        await verifier.verify(token)
    assert info.value.reason == "signature_invalid"


@pytest.mark.asyncio
async def test_verify_malformed_token() -> None:
    """A token that is not a decodable JWT is ``malformed_token``."""
    key, _ = make_keypair()
    verifier = _make_verifier(key)
    with pytest.raises(oauth_mod.TokenValidationError) as info:
        await verifier.verify("not.a.jwt")
    assert info.value.reason == "malformed_token"


@pytest.mark.asyncio
async def test_verify_missing_required_claim() -> None:
    """A token missing a required claim is ``missing_required_claim``."""
    key, pem = make_keypair()
    verifier = _make_verifier(key)
    token = sign(pem, include_exp=False)
    with pytest.raises(oauth_mod.TokenValidationError) as info:
        await verifier.verify(token)
    assert info.value.reason == "missing_required_claim"


@pytest.mark.asyncio
async def test_verify_generic_invalid_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unmapped ``InvalidTokenError`` falls through to ``invalid_token``."""
    key, pem = make_keypair()
    verifier = _make_verifier(key)
    token = sign(pem)

    def _raise(*args: Any, **kwargs: Any) -> None:
        raise jwt.exceptions.InvalidTokenError("generic")

    monkeypatch.setattr(oauth_mod.jwt, "decode", _raise)
    with pytest.raises(oauth_mod.TokenValidationError) as info:
        await verifier.verify(token)
    assert info.value.reason == "invalid_token"


@pytest.mark.asyncio
async def test_verify_insufficient_scope() -> None:
    """A token missing a required scope is ``insufficient_scope``."""
    key, pem = make_keypair()
    verifier = _make_verifier(key, required_scopes=("readiness:admin",))
    token = sign(pem, scope="readiness:read")
    with pytest.raises(oauth_mod.TokenValidationError) as info:
        await verifier.verify(token)
    assert info.value.reason == "insufficient_scope"


@pytest.mark.asyncio
async def test_verify_client_id_from_client_id() -> None:
    """``client_id`` claim resolves the access token's client id."""
    key, pem = make_keypair()
    verifier = _make_verifier(key)
    token = sign(pem, extra={"client_id": "cid", "azp": "azp", "sub": "sub"})
    access = await verifier.verify(token)
    assert access.client_id == "cid"


@pytest.mark.asyncio
async def test_verify_client_id_from_azp() -> None:
    """``azp`` is used when ``client_id`` is absent."""
    key, pem = make_keypair()
    verifier = _make_verifier(key)
    token = sign(pem, extra={"azp": "azp-id", "sub": "sub"})
    access = await verifier.verify(token)
    assert access.client_id == "azp-id"


@pytest.mark.asyncio
async def test_verify_client_id_from_sub() -> None:
    """``sub`` is used when both ``client_id`` and ``azp`` are absent."""
    key, pem = make_keypair()
    verifier = _make_verifier(key)
    token = sign(pem, extra={"sub": "sub-id"})
    access = await verifier.verify(token)
    assert access.client_id == "sub-id"


@pytest.mark.asyncio
async def test_verify_client_id_empty_fallback() -> None:
    """With no id claims the client id resolves to the empty string."""
    key, pem = make_keypair()
    verifier = _make_verifier(key)
    token = sign(pem)
    access = await verifier.verify(token)
    assert access.client_id == ""


@pytest.mark.asyncio
async def test_verify_token_ok_and_failure() -> None:
    """``verify_token`` returns an AccessToken on success, None on failure."""
    key, pem = make_keypair()
    verifier = _make_verifier(key)
    good = sign(pem, scope="readiness:read")
    assert (await verifier.verify_token(good)) is not None
    bad = sign(pem, expires_in=-3600)
    assert (await verifier.verify_token(bad)) is None


def test_verifier_builds_default_cache() -> None:
    """Omitting ``jwks`` builds a cache from the config's JWKS URL."""
    config = oauth_mod.OAuthConfig(ISS, AUD, "https://keys.example.com/jwks")
    verifier = oauth_mod.JWTVerifier(config)
    assert isinstance(verifier._jwks, oauth_mod.JWKSCache)


# --- OAuthResourceMiddleware -----------------------------------------------


class InnerApp:
    """Records the request context the middleware forwards inward."""

    def __init__(self) -> None:
        """Start with no observed call."""
        self.called = False
        self.tenant: str | None = None
        self.scopes: tuple[str, ...] | None = None

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        """Record the forwarded tenant/scopes and answer 200 for HTTP."""
        self.called = True
        if scope["type"] == "http":
            self.tenant = current_tenant()
            self.scopes = current_scopes()
            from starlette.responses import JSONResponse

            await JSONResponse(
                {
                    "tenant": self.tenant or "",
                    "scopes": list(self.scopes),
                }
            )(scope, receive, send)


def _make_middleware(
    key: Any,
    *,
    required_scopes: tuple[str, ...] = (),
    inner: InnerApp | None = None,
) -> tuple[oauth_mod.OAuthResourceMiddleware, InnerApp, oauth_mod.OAuthConfig]:
    """Build the OAuth middleware around a recording inner app."""
    config = oauth_mod.OAuthConfig(
        issuer=ISS,
        audience=AUD,
        jwks_url="https://keys.example.com/jwks",
        required_scopes=required_scopes,
    )
    cache = oauth_mod.JWKSCache("https://keys.example.com/jwks")
    cache._keys = {"k1": pyjwk(key, "k1")}
    cache._fetched_at = float("inf")
    verifier = oauth_mod.JWTVerifier(config, jwks=cache)
    inner = inner if inner is not None else InnerApp()
    middleware = oauth_mod.OAuthResourceMiddleware(inner, verifier, config)
    return middleware, inner, config


async def _request(
    app: Any,
    path: str,
    *,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Issue an in-process GET against ``app``."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        return await client.get(path, headers=headers or {})


@pytest.mark.asyncio
async def test_middleware_metadata_well_known() -> None:
    """The well-known path serves metadata unauthenticated."""
    key, _ = make_keypair()
    middleware, inner, config = _make_middleware(key)
    response = await _request(middleware, oauth_mod.WELL_KNOWN_PATH)
    assert response.status_code == 200
    assert response.json() == oauth_mod.protected_resource_metadata(config)
    assert inner.called is False


@pytest.mark.asyncio
async def test_middleware_metadata_audience_variant() -> None:
    """The audience-derived metadata path also serves metadata."""
    key, _ = make_keypair()
    middleware, _, config = _make_middleware(key)
    path = "/.well-known/oauth-protected-resource/mcp"
    response = await _request(middleware, path)
    assert response.status_code == 200
    assert response.json() == oauth_mod.protected_resource_metadata(config)


@pytest.mark.asyncio
async def test_middleware_no_authorization() -> None:
    """A request with no bearer token is rejected 401 with a challenge."""
    key, _ = make_keypair()
    middleware, inner, _ = _make_middleware(key)
    response = await _request(middleware, "/mcp")
    assert response.status_code == 401
    assert "resource_metadata=" in response.headers["WWW-Authenticate"]
    assert inner.called is False


@pytest.mark.asyncio
async def test_middleware_non_bearer_authorization() -> None:
    """A non-bearer Authorization scheme is rejected 401."""
    key, _ = make_keypair()
    middleware, _, _ = _make_middleware(key)
    response = await _request(
        middleware, "/mcp", headers={"Authorization": "Basic abc"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_middleware_insufficient_scope() -> None:
    """A token lacking a required scope is rejected 403."""
    key, pem = make_keypair()
    middleware, _, _ = _make_middleware(
        key, required_scopes=("readiness:admin",)
    )
    token = sign(pem, scope="readiness:read")
    response = await _request(
        middleware, "/mcp", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403
    assert "insufficient_scope" in response.headers["WWW-Authenticate"]


@pytest.mark.asyncio
async def test_middleware_valid_token_forwards_context() -> None:
    """A valid token is accepted and the tenant/scopes are forwarded."""
    key, pem = make_keypair()
    middleware, inner, _ = _make_middleware(key)
    token = sign(pem, scope="readiness:read premium")
    response = await _request(
        middleware,
        "/mcp",
        headers={
            "Authorization": f"Bearer {token}",
            "X-MCP-Tenant": "acme",
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "tenant": "acme",
        "scopes": ["readiness:read", "premium"],
    }
    assert inner.tenant == "acme"
    assert inner.scopes == ("readiness:read", "premium")


@pytest.mark.asyncio
async def test_middleware_non_http_scope_passthrough() -> None:
    """Non-HTTP scopes bypass auth and reach the inner app."""
    key, _ = make_keypair()
    middleware, inner, _ = _make_middleware(key)
    sent: list[Any] = []

    async def receive() -> dict[str, str]:
        """Yield a single lifespan startup event."""
        return {"type": "lifespan.startup"}

    async def send(message: Any) -> None:
        """Record any outbound ASGI message."""
        sent.append(message)

    await middleware({"type": "lifespan"}, receive, send)
    assert inner.called is True
