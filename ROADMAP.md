<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# `iso20022-readiness-suite-mcp` roadmap

## Mission

The high-level orchestration Model Context Protocol (MCP) server for the
**ISO 20022 MCP Suite** — the White-Label ISO 20022 Readiness & Testing
Gateway. It is an MCP server to the outer agent and an MCP client to the
foundational suite servers, which it composes into readiness scoring,
automated remediation, clearing-profile linting, and bank-response simulation
ahead of the November 2026 ISO 20022 milestones.

## Where we are (v0.0.1, shipped 2026-07-18)

- **4 MCP tools** over stdio, each a thin wrapper over an orchestrator:
  - Profile discovery: `list_profiles` (CBPR+, SEPA_Instant, FedNow,
    Generic) — fully local.
  - Readiness: `run_readiness_check` (detect, structurally validate,
    profile-lint, and score a payload) — composes the foundational
    sub-servers via the meta-client pattern.
  - Remediation: `remediate_payload` (automated fixes, e.g. Nov 2026
    structured addresses) — delegates to `structured-address-fix-mcp`.
  - Simulation: `simulate_bank_response` (emit a pacs.002 status report
    mocking an ACCP / RJCT / PDNG outcome) — fully local.
- **The meta-client pattern**: an MCP server to the outer agent AND an MCP
  client to the foundational suite servers (iso20022-mcp, camt053-mcp,
  pain001-mcp, reconcile-mcp, bankstatementparser-mcp,
  structured-address-fix-mcp), spawned over stdio via `uvx`.
- **Clearing-profile engine**: bundled JSON baseline profiles (open source),
  with a `register()` seam for runtime-loaded premium rule packs.
- **Stdio transport** (FastMCP default): one process per operator, launched
  by the MCP client, no network surface, no authentication needed.
- **Supply chain**: 100% line + branch coverage, OpenSSF Scorecard, SLSA
  Build L3 + PEP 740 sigstore attestations on every release, CycloneDX 1.6 +
  SPDX 2.3 + pip-licenses SBOMs on every GitHub release, NIST SP 800-218 SSDF
  practice mapping in `SECURITY.md`.

## Fast-follow — sister servers, HTTP transport, entitlement gating

Goal: broaden the gateway and support a shared, multi-tenant deployment shape.

- **`iso20022-bank-profile-mcp`** (new sibling server): manage and serve
  bank-specific clearing profiles / rule packs as a first-class server the
  gateway can consume, so operators can point the readiness check at their
  own institution's market practice.
- **`iso20022-evidence-pack-mcp`** (new sibling server): compile the
  readiness findings, remediation diffs, and simulated bank responses into a
  signed, exportable evidence pack for audit and certification workflows.
- **HTTP/SSE transport variant**:
  `iso20022-readiness-suite-mcp --transport=http --bind=…` alongside the
  default stdio, with an optional tenant header forwarded into the
  tool-visible `Context` for multi-tenant scoping, and OAuth 2.1
  resource-server auth (RFC 9728) on the HTTP transport.
- **Premium rule-pack entitlement gating**: gate the higher-tier proprietary
  clearing profiles / remediation packs behind an entitlement claim (matching
  the profile engine's `register()` seam), so operators can license the
  scheme packs they need.

## Later

Goal: post-Nov-2026, field-tested behaviour.

- **Observability**: Prometheus metrics on the MCP layer (request/tool
  counters, tool latency histograms, sub-server failure reasons) and a
  tamper-evident audit chain over orchestrated calls.
- **More guided workflows** as the suite grows (scheme-specific remediation
  packs, batch-message flows, cross-message reconciliation runs).
- **MCP API surface freeze** at the first stable minor: any future tool name
  change becomes a minor-bump event per SemVer.
- **OpenSSF Best Practices** badge progression (Passing → Silver → Gold).

## Out of scope (until a contributor steps up)

- **Embedded LLM**: this server delegates all inference to the client's model
  via MCP; no bundled LLM weights, no hosted inference endpoint.
- **OAuth provider integration**: the planned HTTP transport authenticates by
  validating tokens from your existing authorization server (Okta, Auth0,
  Entra ID, ...); running the authorization server is the operator's job.
- **Reimplementing sub-server logic**: message generation, parsing, and
  low-level validation stay in the foundational sub-servers; this gateway
  orchestrates them, it does not duplicate them.

## How to influence the roadmap

- Open an issue with the proposed tool / profile + the use case it unblocks.
- For larger items, sketch a design in the issue body.
- See [`GOVERNANCE.md`](GOVERNANCE.md) for the decision-making process.
