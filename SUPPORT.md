<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# Support

How to get help with `iso20022-readiness-suite-mcp`, organised by need.

## I want to ask a question

Use **[GitHub Discussions](https://github.com/sebastienrousseau/iso20022-readiness-suite-mcp/discussions)**.
Search first — your question may already have an answer. New
questions get a maintainer response within ~7 days; the community
often answers faster.

## I think I found a bug

File a **[GitHub Issue](https://github.com/sebastienrousseau/iso20022-readiness-suite-mcp/issues/new)**.
Helpful minimum: which MCP client you're using (Claude Desktop, IDE,
custom), the tool that's misbehaving (`list_profiles`,
`run_readiness_check`, `remediate_payload`, `simulate_bank_response`), the
input you sent (the payload text and target profile), and the output you got.
If the failure involves a foundational sub-server, say which one and whether
it is resolvable via `uvx`. A minimal reproducer turns a 2-week investigation
into a 2-hour fix.

## I want to request a feature

Also a **[GitHub Issue](https://github.com/sebastienrousseau/iso20022-readiness-suite-mcp/issues/new)** —
include a *Why* section linking to the rule, RFC, or scheme document
that motivates the ask. The maintainer responds within ~7 days.
Larger asks may go to a 72-hour design comment window per
[`GOVERNANCE.md`](GOVERNANCE.md).

## I need a security disclosure channel

**Don't post security issues publicly.** Use:

- **Preferred**: [GitHub Security Advisories](https://github.com/sebastienrousseau/iso20022-readiness-suite-mcp/security/advisories/new)
  (private + tracked).
- **Alternative**: email
  [sebastian.rousseau@gmail.com](mailto:sebastian.rousseau@gmail.com).

Disclosure timeline (per [`SECURITY.md`](SECURITY.md)): 3-day
acknowledgement / 7-day initial assessment / 30-day fix-or-mitigation.

## I want commercial support

Not formally offered today. The higher-tier proprietary rule packs,
white-label portals, and stateful persistence logs are on the
[roadmap](ROADMAP.md) as paid add-ons; for ad-hoc consulting / integration
help, contact [sebastian.rousseau@gmail.com](mailto:sebastian.rousseau@gmail.com).
For long-term support arrangements, open a Discussion so we can explore
whether a sponsorship or contract makes sense.

## I want to contribute

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the submission process and
[`GOVERNANCE.md`](GOVERNANCE.md) for how decisions are made.
