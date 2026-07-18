# iso20022-readiness-suite-mcp documentation

`iso20022-readiness-suite-mcp` is the **orchestration front door** to the
ISO 20022 MCP Suite. It is an MCP *server* to the outer agent and, at the same
time, an MCP *client* to the foundational servers — the *meta-client* pattern.
It composes structural validation, clearing-profile linting, automated
remediation, and bank-response simulation into higher-order, agent-callable
workflows, and it returns typed, JSON-serialisable data on every path — never a
traceback.

## Start here

- [Quick start](quickstart.md) — install, configure the server in an MCP
  client, and run your first readiness check.
- [Orchestration &amp; the meta-client pattern](orchestration.md) — how the
  server spawns and consumes the foundational servers, and how to point it at
  local or remote sub-servers.

## Reference

- [Clearing profiles](profiles.md) — the baseline profiles (`Generic`,
  `CBPR+`, `SEPA_Instant`, `FedNow`), the rule mini-language, and the
  premium rule-pack seam.

## The tools

| Tool | What it does |
| --- | --- |
| `list_profiles` | Enumerate the available clearing profiles. |
| `run_readiness_check` | Detect → validate → profile-lint → score a payload. |
| `remediate_payload` | Apply automated remediation (e.g. structured addresses). |
| `simulate_bank_response` | Emit a deterministic `pacs.002` status report. |

## Part of the ISO 20022 MCP Suite

This server orchestrates the foundational servers of the suite
(`iso20022-mcp`, `camt053-mcp`, `pain001-mcp`, `reconcile-mcp`,
`bankstatementparser-mcp`, `structured-address-fix-mcp`). See the
[project README](https://github.com/sebastienrousseau/iso20022-readiness-suite-mcp)
for the full suite map.
