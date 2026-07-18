<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# `iso20022-readiness-suite-mcp` governance

This document describes how `iso20022-readiness-suite-mcp` is run, how
decisions are made, and how to take on responsibility for it.
`iso20022-readiness-suite-mcp` is the high-level orchestration server of the
**ISO 20022 MCP Suite**; the suite-wide conventions (CI floor, release
pipeline, PR style) are shared across the sibling repositories. This document
covers the orchestration-server-specific bits.

## Mission and scope

`iso20022-readiness-suite-mcp` is the Model Context Protocol (MCP) server that
composes the foundational suite servers (iso20022-mcp, camt053-mcp,
pain001-mcp, reconcile-mcp, bankstatementparser-mcp, structured-address-fix-mcp)
into higher-order readiness workflows via the meta-client pattern. Changes are
weighed against the same criterion as the rest of the suite:
**correctness, security, and clarity over feature breadth**.

A change is in-scope if it adds or hardens an orchestration tool, a clearing
profile, a remediation policy, or the bank-response simulator, or improves the
agent-driven workflow shape. A change is out-of-scope if it duplicates logic
that belongs in a foundational sub-server, or ships features that depend on a
particular client (e.g. Claude-specific extensions).

## Roles + decision making

| Role | Who | Can |
| :--- | :--- | :--- |
| **Maintainer** | Listed in [`MAINTAINERS.md`](MAINTAINERS.md) | Merge PRs, cut releases, triage, set direction |
| **Contributor** | Anyone with a merged PR | Propose changes, review, discuss |
| **User** | Everyone | File issues, ask questions, request features |

- Day-to-day changes land via PR with maintainer approval (conventional
  commits + signed commits + branch policy from the suite STYLEGUIDE).
- Larger changes (new tool surface, new transport, new sub-server dependency,
  dependency additions) require a tracking GitHub Issue + 72-hour comment
  window + maintainer agreement.
- Releases are cut against a v0.X milestone; signed tag + OIDC publish
  to PyPI with PEP 740 attestations.
- Security disclosures: 3-day ack / 7-day assessment / 30-day fix per
  [`SECURITY.md`](SECURITY.md).

## Cross-suite consistency

All packages in the ISO 20022 MCP Suite share the same CI floor, release
pipeline, and governance documents. Cross-suite policy changes are agreed
across the sibling repositories and mirrored so the servers stay aligned.

## Becoming a maintainer

See the path in [`MAINTAINERS.md`](MAINTAINERS.md).

## Updating this document

PR with the 72-hour comment window for anything material. The lead
maintainer has final say but engages with substantive feedback before
merging.
