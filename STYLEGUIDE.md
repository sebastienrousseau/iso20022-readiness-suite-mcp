<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# `iso20022-readiness-suite-mcp` style guide

`iso20022-readiness-suite-mcp` follows the shared conventions of the
**ISO 20022 MCP Suite**. Those conventions are the single source of truth for:

- Voice + spelling conventions (British prose, American code, no em-dashes,
  no emojis outside the standard checkmark/cross in supported-versions
  tables).
- README structure (section template + badge order).
- CHANGELOG structure (Keep-a-Changelog + suite Quality gates).
- SECURITY.md structure (including the NIST SSDF practice mapping).
- SUPPORT.md / CONTRIBUTING.md structure.
- CI floor (test + lint + security + docstring-coverage gates + release-only
  gates).
- PR style (conventional commits + signed commits + branch policy).
- Branch naming, issue filing, naming conventions.

## Local additions

`iso20022-readiness-suite-mcp` follows the suite convention that **MCP tool
names use the `verbNoun` snake_case pattern**:

```
list_profiles            # not get_profiles or profiles()
run_readiness_check      # not readiness or check_readiness()
remediate_payload        # not fix_payload or payload_remediate
simulate_bank_response   # not bank_response or mock_response()
```

This makes tool names read naturally as English imperatives in agent
prompts.

Two orchestration-specific conventions:

- **Errors are data, not tracebacks.** Every tool returns an
  `{"error": ...}` payload on failure; sub-server failures are captured as a
  typed `ToolOutcome` and never raised across the tool boundary.
- **Payloads are content, not paths.** Tools accept raw ISO 20022 message text
  (`payload_content` / `inbound_payload`), never a server filesystem path.

## Updating

If you find divergence between this repo's practice and the shared suite
conventions, the suite wins; open a PR to align this repo (and/or fix the
deviation).
