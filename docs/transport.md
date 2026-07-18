# HTTP transport & authentication

`iso20022-readiness-suite-mcp` speaks **stdio** by default — launched by a
local MCP client, one process per operator, with no network surface and **no
authentication needed**. For shared, multi-tenant deployments it also offers an
**optional streamable-HTTP transport** with OAuth 2.1 resource-server auth
(RFC 9728). This page covers configuring and running the HTTP transport.

## stdio (default) — no auth

Nothing to configure. The console entry point starts the server over stdio:

```sh
iso20022-readiness-suite-mcp
```

This is the right transport for a single operator driving the gateway from an
MCP client (Claude Desktop, an IDE plugin, an agent framework). It has no
authentication surface — the client owns the process lifecycle.

## Streamable HTTP — opt in

Select the HTTP transport with `--transport=http`. The default `--bind` is
`127.0.0.1:8080`, i.e. **loopback-only**: nothing outside the host can reach it
until you bind a routable address explicitly.

```sh
# Loopback only (default bind)
iso20022-readiness-suite-mcp --transport=http

# Exposed on all interfaces
iso20022-readiness-suite-mcp --transport=http --bind=0.0.0.0:8080
```

The HTTP transport **requires authentication**. Starting `--transport=http`
with neither OAuth nor a static token configured is refused with a `SystemExit`
rather than serving an unauthenticated endpoint. Two auth modes are supported,
resolved strongest first.

## OAuth 2.1 resource server (RFC 9728) — production

When the `ISO20022_READINESS_OAUTH_*` environment variables are set, the server
acts as an OAuth 2.1 **resource server**: it validates every
`Authorization: Bearer <jwt>` against your authorization server's JWKS. It does
**not** issue tokens — running the authorization server (Okta, Auth0, Entra ID,
…) is the operator's job.

| Variable | Required | Meaning |
|---|---|---|
| `ISO20022_READINESS_OAUTH_ISSUER` | yes | Authorization server issuer identifier; the JWT `iss` claim must match it exactly. |
| `ISO20022_READINESS_OAUTH_AUDIENCE` | yes | This server's canonical resource URI (RFC 8707); the JWT `aud` claim must contain it. |
| `ISO20022_READINESS_OAUTH_JWKS_URL` | no | JWKS document URL. Defaults to `<issuer>/.well-known/jwks.json`. |
| `ISO20022_READINESS_OAUTH_SCOPES` | no | Space-separated scopes every token must carry. Unset/empty means no scope gate. |

Setting some but not both of `ISSUER` / `AUDIENCE` is a **partial
configuration** and is refused (`SystemExit`), so a typo'd deployment fails
loudly rather than falling back to weaker auth.

```sh
ISO20022_READINESS_OAUTH_ISSUER=https://auth.example.com \
ISO20022_READINESS_OAUTH_AUDIENCE=https://mcp.example.com/mcp \
ISO20022_READINESS_OAUTH_SCOPES="readiness:read" \
  iso20022-readiness-suite-mcp --transport=http --bind=0.0.0.0:8080
```

### What is validated

Each bearer JWT is checked for:

- **Signature** against the JWKS keys, with key rotation — an unknown `kid`
  triggers a JWKS refresh. The verification algorithm is taken from the JWKS
  key, never from the token header, so `none` / HMAC downgrades are structurally
  impossible with an asymmetric key set.
- **`iss`** matches the configured issuer, and **`aud`** contains the configured
  audience.
- **`exp`** / **`nbf`** with a small clock-skew leeway.
- **Required scopes**, when `OAUTH_SCOPES` is set.

### Protected-resource metadata (RFC 9728)

The RFC 9728 §2 protected-resource metadata document is served
**unauthenticated** at:

```
GET /.well-known/oauth-protected-resource
```

It advertises the `resource` (your audience), the `authorization_servers`
(your issuer), `bearer_methods_supported`, and — when configured — the required
`scopes_supported`.

### Rejections

A request that fails validation is rejected with:

- **`401 Unauthorized`** for a missing / malformed / invalid token, or
- **`403 Forbidden`** for `insufficient_scope`,

each carrying an RFC 6750 / RFC 9728 `WWW-Authenticate: Bearer …` challenge
whose `resource_metadata` parameter points a client at the metadata endpoint
above. The token is never echoed back.

## Static bearer token — dev mode only

When no `ISO20022_READINESS_OAUTH_*` variables are set, the HTTP transport
accepts a single shared secret from `ISO20022_READINESS_TOKEN` instead
(compared with `hmac.compare_digest`). Every HTTP request must then send
`Authorization: Bearer <secret>`.

```sh
ISO20022_READINESS_TOKEN=s3cret \
  iso20022-readiness-suite-mcp --transport=http --bind=127.0.0.1:8080
```

This is **explicitly dev-mode**: one shared secret, no expiry, no scopes, no
key rotation. Use it for local development against the loopback bind, not for a
production, internet-facing deployment. If **both** OAuth and the static token
are configured, OAuth wins and the static token is ignored (a warning is
logged).

## Tenant scoping — the `X-MCP-Tenant` header

HTTP callers may send an optional `X-MCP-Tenant` request header. It is
forwarded into a per-request tenant context for the duration of that request,
and the authenticated token's OAuth scopes are exposed alongside it. Tools read
both through the request context, so tool code can scope or gate behaviour by
tenant or entitlement scope without branching on the transport — under stdio
both are simply empty.

## Production vs dev at a glance

| | stdio (default) | HTTP + static token | HTTP + OAuth 2.1 |
|---|---|---|---|
| Intended use | Single operator, local | Local development | Production, multi-tenant |
| Auth | None (client owns the process) | One shared secret | JWT validated against a JWKS |
| Token lifecycle | — | No expiry, no scopes | `exp` / `nbf`, scopes, key rotation |
| Network surface | None | Bind loopback | Bind routable, behind TLS |
| Metadata endpoint | — | — | `/.well-known/oauth-protected-resource` |

For production, prefer OAuth 2.1, bind behind a TLS-terminating proxy, and
restrict the audience to this server's canonical resource URI. The static token
is a convenience for getting the HTTP transport up locally, not a production
credential.

## New runtime dependencies

The HTTP transport pulls in `pyjwt[crypto]`, `httpx`, `starlette`, and
`uvicorn`. These are declared as regular runtime dependencies; a stdio-only
deployment installs them but never imports them (the `http` package is imported
lazily only when `--transport=http` is selected).

## See also

- [README — HTTP transport & authentication](https://github.com/sebastienrousseau/iso20022-readiness-suite-mcp/blob/main/README.md#http-transport--authentication)
- [`CHANGELOG.md`](https://github.com/sebastienrousseau/iso20022-readiness-suite-mcp/blob/main/CHANGELOG.md) — the v0.0.2 release notes
- [Quickstart](quickstart.md) — install → MCP client config → first conversation
- [Orchestration](orchestration.md) — the meta-client pattern
