# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.0.1]: https://github.com/sebastienrousseau/iso20022-readiness-suite-mcp/releases/tag/v0.0.1
