# Security Policy

The iso20022-readiness-suite-mcp maintainers take the security of this project
seriously. This document explains which versions receive security updates and
how to report a vulnerability responsibly.

iso20022-readiness-suite-mcp is the high-level orchestration Model Context
Protocol (MCP) server of the **ISO 20022 MCP Suite** — the "White-Label ISO
20022 Readiness & Testing Gateway". It is an MCP *server* to the outer agent
and an MCP *client* to the foundational suite servers (iso20022-mcp,
camt053-mcp, pain001-mcp, reconcile-mcp, bankstatementparser-mcp,
structured-address-fix-mcp), which it spawns over stdio via the meta-client
pattern. It adds readiness scoring, automated remediation, clearing-profile
linting (CBPR+, SEPA_Instant, FedNow, Generic), and bank-response simulation
ahead of the November 2026 ISO 20022 milestones.

## Supported Versions

Security fixes are applied to the latest released minor version. While the
project is in its `0.x` series, only the most recent release line receives
security updates.

| Version | Supported          |
| ------- | ------------------ |
| 0.0.2   | :white_check_mark: |
| < 0.0.2 | :x:                |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues,
discussions, or pull requests.**

We support coordinated disclosure. To report a vulnerability, use either of the
following private channels:

- **GitHub Security Advisories** (preferred): open a private report via the
  repository's
  [Security tab → "Report a vulnerability"](https://github.com/sebastienrousseau/iso20022-readiness-suite-mcp/security/advisories/new).
- **Email**: contact the maintainer at
  [sebastian.rousseau@gmail.com](mailto:sebastian.rousseau@gmail.com).

When reporting, please include as much of the following as possible:

- A description of the vulnerability and its potential impact.
- Steps to reproduce, or a proof-of-concept.
- The affected version(s) and environment (Python version, OS).
- Any known mitigations or workarounds.

## Response Timeline

We aim to meet the following targets, on a best-effort basis:

| Stage                     | Target                          |
| ------------------------- | ------------------------------- |
| Acknowledge receipt       | Within 3 business days          |
| Initial assessment        | Within 7 business days          |
| Fix or mitigation plan    | Within 30 days of confirmation  |
| Public disclosure         | Coordinated, after a fix ships  |

We will keep you informed of progress throughout the process and will credit
reporters in the advisory unless anonymity is requested.

## Scope

The following are in scope:

- The `iso20022-readiness-suite-mcp` MCP server as published in this
  repository, including the FastMCP tools it exposes over stdio
  (`list_profiles`, `run_readiness_check`, `remediate_payload`,
  `simulate_bank_response`) and the error envelopes it returns.
- The **meta-client seam**: the way the server spawns and calls the
  foundational sub-servers over stdio (`StdioSubServerInvoker`), including the
  command map used to launch them and the handling of sub-server failures
  (spawn errors, missing servers, tool errors are returned as data, never
  raised across the tool boundary).
- Handling of agent-supplied tool arguments and the payloads returned to
  agents, including error envelopes. Inbound payloads are accepted as raw
  string content, never as server filesystem paths.
- XML parsing reached through the clearing-profile engine
  (`ProfileEngine.apply`), which parses payloads with `defusedxml` only
  (XXE / billion-laughs hardened).
- Input validation for clearing-profile identifiers, status reason codes, and
  the simulated-response behaviour enum.

The following are generally out of scope:

- Vulnerabilities in the foundational sub-servers themselves (iso20022-mcp,
  camt053-mcp, pain001-mcp, reconcile-mcp, bankstatementparser-mcp,
  structured-address-fix-mcp); please report those against their respective
  repositories.
- Vulnerabilities in third-party dependencies (please report those upstream;
  we will track and update affected dependencies via Dependabot).
- Issues requiring a compromised host, malicious local configuration, or
  physical access — including a maliciously configured sub-server command map
  that points the invoker at an attacker-controlled binary.
- Denial of service caused by intentionally malformed, multi-gigabyte inputs
  beyond documented usage.

Thank you for helping keep iso20022-readiness-suite-mcp and its users safe.

## NIST SSDF practice mapping

This repository follows the practices of the **NIST Secure Software
Development Framework (SP 800-218 Rev 1.1)**. The table below maps
each SSDF practice that applies to an open-source Python project to
the concrete control(s) that implement it in this repo.

| SSDF practice | How this repo addresses it |
| :--- | :--- |
| **PO.1** Define security requirements | This `SECURITY.md`, plus the in-scope/out-of-scope sections above. |
| **PO.3** Implement supporting toolchains | `pyproject.toml`; `.github/workflows/ci.yml` (test + lint + security scan); `.github/workflows/scorecard.yml`. |
| **PO.4** Define and use criteria for software security checks | CI enforces tests on Python 3.10/3.11/3.12/3.13, ruff lint, black formatting, mypy `--strict`, bandit security scan, interrogate docstring coverage; Scorecard runs weekly. |
| **PO.5** Implement and maintain secure environments | PyPI Trusted Publishing (OIDC, no long-lived tokens); branch protection + signed commits on `main`; per-workflow `permissions:` minimisation. |
| **PS.1** Protect all forms of code from unauthorized access and tampering | Signed commits (SSH ed25519); branch protection; required PR reviews; `persist-credentials: false` on Scorecard checkout. |
| **PS.2** Provide a mechanism for verifying software release integrity | Signed git tags; `actions/attest-build-provenance` SLSA L3 provenance attestations; PEP 740 sigstore attestations on PyPI uploads (`pypa/gh-action-pypi-publish` with `attestations: true`). |
| **PS.3** Archive and protect each software release | GitHub Releases pin the exact `dist/*` artifacts; CycloneDX 1.6 + SPDX 2.3 SBOMs and a pip-licenses manifest attached to every release; PyPI is the immutable archive. |
| **PW.1** Design software to mitigate security risks | XML payloads are parsed with `defusedxml` only (no XXE / billion-laughs); the orchestrator returns serialised `{"error": ...}` payloads rather than raising into client transports; every sub-server failure is captured as a typed `ToolOutcome`. |
| **PW.4** Reuse well-secured software when feasible | Dependencies pinned via pyproject; Dependabot grouped weekly + separate security-update group; updates reviewed before merge. |
| **PW.5** Adhere to secure coding practices | `ruff`, `bandit -ll`, strict `mypy`, code review on every PR. |
| **PW.6** Configure build processes to improve security | Reproducible builds via `poetry build` with locked dependencies; CI uses SHA-pinned actions; minimum-required GH Actions permissions. |
| **PW.7** Review and analyze human-readable code | All changes go through PRs with required review; CodeQL static analysis runs on push/PR; ruff + mypy + bandit on every change. |
| **PW.8** Test executable code | pytest on Python 3.10–3.13 at 100% line + branch coverage; the orchestration logic is exercised against an injected fake sub-server so no real sub-processes are spawned in the test suite. |
| **PW.9** Configure software with secure defaults | Stdio transport binds to the local process owner only (no network listener); tools return errors as data instead of raising into the client. |
| **RV.1** Identify and confirm vulnerabilities on an ongoing basis | Dependabot daily; `bandit` in CI; OpenSSF Scorecard weekly; GitHub Security Advisories accept reports. |
| **RV.2** Assess, prioritise, and remediate vulnerabilities | Coordinated-disclosure timeline above (3-day ack / 7-day assessment / 30-day fix); CHANGELOG + advisory at fix publication. |
| **RV.3** Analyze root causes | Each security advisory captures root cause + remediation in the GitHub Security Advisory body; lessons feed back into added regression tests. |

Cross-suite practices (organisation roles, multi-package release governance)
are shared across the ISO 20022 MCP Suite repositories.

## Accepted OpenSSF Scorecard findings

The suite runs [OpenSSF Scorecard](https://securityscorecards.dev/) weekly and
treats its results as advisory. The checks below are **accepted risks**: they
cannot be resolved by code or configuration for a single-maintainer
open-source project at v0.0.1, and are recorded here so their status is
explicit.

- **Branch-Protection** — `main` is protected: pull requests are required,
  with a required status check (`Lint & Type Check`), dismissal of stale
  reviews, linear history, and no force-pushes or deletions. Scorecard's
  highest tier also wants `enforce_admins` enabled; we deliberately leave it
  **off** so the sole maintainer can still merge approved release/security
  PRs without a second account (see [`MAINTAINERS.md`](MAINTAINERS.md)). This
  is an accepted trade-off.
- **Code-Review** — Scorecard expects each change to be approved by a
  *second* reviewer. With a single maintainer this is structurally
  impossible; changes still go through pull requests with CI gating.
  Accepted until a second maintainer joins.
- **Maintained** — a heuristic over recent commit/issue cadence that can lag
  immediately after a release lull. The project is actively maintained (see
  the commit history and the lockstep release process).
- **Fuzzing** — no continuous fuzzing harness ships in v0.0.1. The
  attacker-reachable parsing surface (the clearing-profile engine) is
  defusedxml-backed, and the orchestration seam is exercised against an
  injected fake; a fuzzing target may be added later. Accepted for now.
- **CII-Best-Practices** — the project is not yet registered for an OpenSSF
  Best Practices badge (a manual enrolment). Accepted until enrolled.

All **code-fixable** Scorecard checks are satisfied: Pinned-Dependencies
(SHA-pinned GitHub Actions + hash-pinned `pip` installs, resolved and
hash-pinned from PyPI in `requirements/*.txt`), Token-Permissions
(least-privilege workflow tokens), and SAST (CodeQL on push/PR). One residual
Pinned-Dependencies signal is accepted: `pip install .` (installing this
repository's own checked-out source in `mcp-inspect.yml` and the `Dockerfile`),
which has no external version or hash to pin.
