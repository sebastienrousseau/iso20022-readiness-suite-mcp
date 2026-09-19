# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `--transport streamable-http` and `--transport sse`, with `--host` and
  `--port`. Streamable HTTP serves both current protocol revisions
  (2026-07-28 stateless with `server/discover`, and 2025-11-25 with the
  `initialize` handshake) on one endpoint and streams responses as
  server-sent events; `sse` serves the older HTTP+SSE transport. stdio
  stays the default and is unchanged, and so is the authenticated
  `--transport http` with `--bind`. ADR 0001 records the decision.

### Fixed

- The Glama and MCP-registry manifests (`glama.json`, `server.json`) named a
  release several versions old, so the directory listings advertised a stale
  install; both are stamped to the shipped version and a CI job now fails
  when they, the package version and the changelog disagree.

### Changed

- Sub-servers stay running between calls. The gateway used to launch the
  underlying server (through `uvx`) for every tool call and tear it down
  after, which put about two seconds on each `remediate_payload`; the
  first call to a server now opens a session that later calls reuse, a
  failed session is dropped and relaunched, and an idle one closes after
  five minutes.
- The `readiness_review` prompt describes its `target_profile` argument.

## [0.0.5] - 2026-08-29

Adds the scheduled release-consistency check this repository was
missing, and refreshes the shared conformance gate.

### Added

- `scripts/check_suite_consistency.py` and a scheduled **Release
  Consistency** workflow compare this tree against what is actually
  published on PyPI. A version bumped in the tree and never released
  breaks nothing — the tree is consistent, the tests pass, the changelog
  is written — and only the index disagrees. That has happened three
  times in this suite, each time stranding a security floor that reached
  nobody.
- The check distinguishes the two directions: a tree ahead of the index
  is the expected transient between merging a bump and pushing its tag,
  while a tree *behind* it means a release was cut from somewhere other
  than this branch.

### Changed

- Refreshed `tests/test_suite_conformance.py` to the current canonical
  copy. This repository was carrying a 24-invariant version; the
  twenty-fifth is the one that requires the check added above, so it had
  been conformant only against an older bar.

## [0.0.4] - 2026-08-28

Brings this repository onto the **suite conformance gate**.

### Added

- **`benches/bench_simulate_response.py`** — the cost of rehearsing against
  a bank that has not switched on yet. Rehearsal means volume: a harness
  replays a whole batch, and a real batch is hundreds of `<PmtInf>` blocks
  rather than the single one in the fixtures.

  **Simulation is linear** in payload size — `us/block` moves **0.98x**
  between 10 and 5,000 blocks. Total cost tracks the document, because the
  whole inbound payload is parsed. That is defensible, though a pacs.002
  needs only the group header and the references, so there is room to read
  less. What would be a defect is that number climbing.

  **The three behaviours are close.** `ACCP` 0.544 ms, `RJCT` 0.555 ms,
  `PDNG` 0.655 ms on the same payload — no path does markedly more work
  than the others.

  **Refusal is the cheap path.** `RJCT` without a reason code is refused in
  **0.009 ms** against 0.544 ms for the cheapest real response, 60x
  cheaper. That is the right way round: validation that builds a response
  and then discards it wastes the work on exactly the input a fuzzing
  harness sends most of.

  Nothing asserts a timing threshold. CI runs `--quick`, so a benchmark
  that stops compiling fails the build rather than rotting.

- **`tests/test_suite_conformance.py`** — invariants shared by every
  repository in the suite, vendored from one canonical copy and
  checksummed by its own test.

### Changed

- CI lints, formats and runs `benches/` alongside everything else.
- `tomli` (on 3.10) and `packaging` are named in the dev dependency group;
  the conformance gate parses `pyproject.toml` and needs both.
- `tests/test_suite_conformance.py` is excluded from black: it is
  generated, and the suite uses three different line lengths.

## [0.0.3] - 2026-08-21

### Added

- **MCP prompts and resources** for parity across the MCP trinity.
- **Optional OpenTelemetry tracing** behind the `[otel]` extra.
- **README and docs snippets are executed in CI**, so documented
  examples cannot silently stop working.
- **An example covering the HTTP transport's OAuth 2.1 (RFC 9728)
  configuration.**

### Fixed

- **`cryptography` 50.0.0**, the release that patches the outstanding
  advisory. The previous ceiling made it unresolvable.
- **`mcp` capped below 2.0**, restoring the FastMCP API the server is
  written against.

### Changed

- **A `lockfile` CI job.** `release.yml` installs with poetry and CI did
  not, so a stale `poetry.lock` was undetectable until a release — with
  the tag already public.
- Security policy's supported-versions table reconciled.
- Dependency and GitHub Actions updates consolidated across several
  Dependabot batches.

## [0.0.2] - 2026-07-18

Adds an **optional streamable-HTTP transport** for shared, multi-tenant
deployments, alongside the default stdio transport. stdio remains fully
supported and unchanged (one process per operator, no authentication surface);
the HTTP transport is strictly opt-in via `--transport=http`.

### Added

- **Optional streamable-HTTP transport**: `iso20022-readiness-suite-mcp
  --transport=http --bind=HOST:PORT`. The default transport stays `stdio`; the
  default `--bind` is `127.0.0.1:8080` (loopback-only, so exposing the endpoint
  is an explicit opt-in, e.g. `--bind=0.0.0.0:8080`).
- **OAuth 2.1 resource-server authentication (RFC 9728)** on the HTTP
  transport, enabled when the `ISO20022_READINESS_OAUTH_*` environment
  variables are set:
  - `ISO20022_READINESS_OAUTH_ISSUER` (required) — the authorization server;
    the JWT `iss` claim must match it exactly.
  - `ISO20022_READINESS_OAUTH_AUDIENCE` (required) — this server's canonical
    resource URI (RFC 8707); the JWT `aud` claim must contain it.
  - `ISO20022_READINESS_OAUTH_JWKS_URL` (optional) — JWKS document URL,
    defaulting to `<issuer>/.well-known/jwks.json`.
  - `ISO20022_READINESS_OAUTH_SCOPES` (optional) — space-separated scopes every
    token must carry.
  Bearer JWTs are validated against the JWKS (signature with key rotation on an
  unknown `kid`), including `iss` / `aud` / `exp` / `nbf` and any required
  scopes. The RFC 9728 protected-resource metadata is served unauthenticated at
  `/.well-known/oauth-protected-resource`. Failures return `401`
  (`403` for `insufficient_scope`) with an RFC 6750 / RFC 9728
  `WWW-Authenticate` challenge carrying the `resource_metadata` URL.
- **Static dev-mode bearer token fallback** via `ISO20022_READINESS_TOKEN`
  (compared with `hmac.compare_digest`) for local development when no OAuth
  server is available. Explicitly dev-mode: single shared secret, no expiry, no
  scopes. When both OAuth and the static token are configured, OAuth wins and
  the static token is ignored. Starting `--transport=http` with neither
  configured is refused (`SystemExit`).
- **Multi-tenant scoping**: an optional `X-MCP-Tenant` request header is
  forwarded into a per-request tenant context, and the authenticated token's
  OAuth scopes are exposed to tools, so tool code can scope or gate behaviour
  without branching on the transport (both are simply empty under stdio).
- **New runtime dependencies** (pulled in for the HTTP transport):
  `pyjwt[crypto]`, `httpx`, `starlette`, `uvicorn`.

## [0.0.1] - 2026-07-18

Initial release: the high-level orchestration Model Context Protocol (MCP)
server of the **ISO 20022 MCP Suite** — the White-Label ISO 20022 Readiness &
Testing Gateway. It is an MCP server to the outer agent and an MCP client to
the foundational suite servers, which it composes into readiness scoring,
remediation, clearing-profile linting, and bank-response simulation ahead of
the November 2026 ISO 20022 milestones.

### Added

- **4 MCP tools over stdio**, each a thin wrapper over an orchestrator that
  returns typed, JSON-serialisable data and an `{"error": ...}` payload on any
  failure (never a traceback):
  - `list_profiles` — list the available clearing profiles (CBPR+,
    SEPA_Instant, FedNow, Generic) with their market practice and custom
    rules. Fully local; no sub-servers required.
  - `run_readiness_check` — detect, structurally validate, profile-lint, and
    score a payload's readiness against a clearing profile. Composes the
    foundational sub-servers via the meta-client pattern.
  - `remediate_payload` — apply automated remediation (e.g. Nov 2026
    structured addresses) driven by a clearing profile, delegating to
    `structured-address-fix-mcp`.
  - `simulate_bank_response` — emit a pacs.002 status report mocking a bank's
    ACCP / RJCT / PDNG response. Fully local; no sub-servers required.
- **The meta-client pattern**: an MCP server to the outer agent AND an MCP
  client to the foundational suite servers (iso20022-mcp, camt053-mcp,
  pain001-mcp, reconcile-mcp, bankstatementparser-mcp,
  structured-address-fix-mcp), spawned over stdio via `uvx`. The orchestration
  logic depends only on a `SubServerInvoker` protocol, so it is exercised in
  tests against an injected fake without spawning real sub-processes.
- **Clearing-profile engine**: bundled JSON baseline profiles (open source),
  with a `register()` seam for runtime-loaded premium rule packs; XML parsed
  with `defusedxml` only.
- **`iso20022-readiness-suite-mcp` console entry point** launching the FastMCP
  server over stdio (`--version` supported).
- **Read-only / open-world tool annotations**: the orchestration tools are
  marked read-only, non-destructive, non-idempotent, open-world (they reach
  external sub-servers); the local simulator and profile lister are
  closed-world.
- **Supply chain**: 100% line + branch coverage gate, ruff + black +
  mypy `--strict` + bandit + interrogate in CI across Python 3.10/3.11/3.12/
  3.13; OpenSSF Scorecard; SLSA Build L3 provenance + PEP 740 sigstore
  attestations on release; CycloneDX 1.6 + SPDX 2.3 + pip-licenses SBOMs on
  every GitHub release; NIST SP 800-218 SSDF practice mapping in
  `SECURITY.md`; MCP registry + Glama directory manifests.

[0.0.2]: https://github.com/sebastienrousseau/iso20022-readiness-suite-mcp/releases/tag/v0.0.2
[0.0.1]: https://github.com/sebastienrousseau/iso20022-readiness-suite-mcp/releases/tag/v0.0.1
