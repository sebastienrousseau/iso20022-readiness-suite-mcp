<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# iso20022-readiness-suite-mcp Architecture

A map of the codebase for new contributors and maintainers. The goal is
that anyone can navigate, extend, and reason about
iso20022-readiness-suite-mcp without prior context.

## The pipeline

```
MCP client (Claude Desktop, IDE, agent, gateway)
        |  stdio (JSON-RPC), streamable HTTP, SSE,
        |  or authenticated streamable HTTP (http/transport.py)
        v
iso20022_readiness_suite_mcp/server.py   (MCPServer: 4 tools, 2 resources, 1 prompt)
        |  thin typed wrappers
        v
orchestrators/                            (detect -> validate -> profile-lint -> score;
        |                                  remediate; simulate a pacs.002)
        |  policies/engine.py (clearing profiles), reports/compiler.py (scoring)
        v
clients/sub_server.py                     (the meta-client: spawns the foundational
        |                                  servers over stdio via uvx, pools sessions)
        v
iso20022-mcp, camt053-mcp, pain001-mcp, reconcile-mcp,
bankstatementparser-mcp, structured-address-fix-mcp
```

The server is an MCP *server* to the outer agent and an MCP *client* to
the foundational servers of the suite. Tools are deliberately thin: each
one calls an orchestrator, and the orchestrators compose the sub-servers'
results into a readiness verdict, a remediated payload or a simulated
bank response. Message parsing, generation and low-level validation stay
in the sub-servers; this repository owns the composition.

## Module map

| Area | Module | Responsibility |
| :--- | :--- | :--- |
| **Server** | `iso20022_readiness_suite_mcp/server.py` | The MCPServer, all tool / resource / prompt registrations, the argparse `main()` |
| **Entry point** | `iso20022_readiness_suite_mcp.server:main` (console script: `iso20022-readiness-suite-mcp`) | Launches the server over stdio, over streamable HTTP / SSE with `--transport` (`_cli.py`, `_transports.py`, ADR 0001), or over authenticated streamable HTTP with `--transport http --bind` (`http/transport.py`) |
| **Suite command line** | `iso20022_readiness_suite_mcp/_cli.py`, `iso20022_readiness_suite_mcp/_transports.py` | `--host`/`--port` and the transport dispatch, copied verbatim into every server of the suite; work on mcp 1.x and 2.x |
| **Meta-client** | `iso20022_readiness_suite_mcp/clients/sub_server.py` | `StdioSubServerInvoker`: spawns a foundational server over stdio through `uvx`, keeps the session open for later calls, relaunches a failed one and closes an idle one after five minutes; the `SubServerInvoker` protocol is the seam the tests fake |
| **Orchestrators** | `iso20022_readiness_suite_mcp/orchestrators/routing.py`, `readiness.py`, `simulator.py` | Message-type detection and validation routing; the readiness and remediation flows; deterministic `pacs.002` simulation (ACCP / RJCT / PDNG) |
| **Policies** | `iso20022_readiness_suite_mcp/policies/engine.py`, `data/` | The clearing-profile engine over the bundled JSON profiles (Generic, CBPR+, SEPA_Instant, FedNow) and the `register()` seam for runtime-loaded rule packs |
| **Reports** | `iso20022_readiness_suite_mcp/reports/compiler.py` | Readiness scoring and the evidence summary |
| **Schemas** | `iso20022_readiness_suite_mcp/models.py`, `errors.py` | Pydantic request / response models; the error taxonomy every tool turns into an `{"error": ...}` payload |
| **Authenticated HTTP** | `iso20022_readiness_suite_mcp/http/transport.py`, `http/oauth.py`, `http/context.py` | Streamable HTTP with mandatory bearer auth (static `ISO20022_READINESS_TOKEN` in dev mode, OAuth 2.1 resource-server JWT validation per RFC 9728 in production), `X-MCP-Tenant` scoping and the per-request context tools read |
| **Tracing** | `iso20022_readiness_suite_mcp/tracing.py` | Opt-in OpenTelemetry tracing behind the `[otel]` extra (`--otel-endpoint`) |
| **SDK shim** | `iso20022_readiness_suite_mcp/_mcp_compat.py` | One import surface over mcp 1.x (`FastMCP`) and 2.x (`MCPServer`) |
| **Version** | `iso20022_readiness_suite_mcp/__init__.py` | Single source of truth (`__version__`) |
| **Tests** | `tests/` | In-process regressions per module with a fake sub-server invoker, the HTTP transport and OAuth tests, executed README / docs snippets, the suite conformance invariants |
| **Benchmarks** | `benches/bench_simulate_response.py` | The cost of simulating a response across payload sizes; CI runs `--quick` |
| **Examples** | `examples/` | One runnable script per usage shape, executed by a test |
| **Release helpers** | `scripts/verify_versions.py`, `scripts/check_suite_consistency.py` | Version sources agree; the tree matches what PyPI publishes |

## Tools, resources, prompts

The current MCP surface:

- **Tools** (4) - `list_profiles` and `simulate_bank_response` run
  locally; `run_readiness_check` and `remediate_payload` reach the
  sub-servers, which must be resolvable through `uvx` or an overridden
  command map.
- **Resources** (2) - `readiness://profiles` and the templated
  `readiness://profile/{profile_id}`.
- **Prompts** (1) - `readiness_review`.

## Key design decisions

- **Orchestration, not duplication.** The gateway composes the
  foundational servers; it does not re-implement their parsing or
  validation. A new capability that belongs to one message type goes
  into that server, and the gateway calls it.
- **Errors as data.** Tools do not raise on bad input or on a
  sub-server failure. A `ReadinessError` or a failed `ToolOutcome`
  becomes an `{"error": ...}` payload so the agent can reason about the
  failure without parsing tracebacks.
- **Sub-servers spawned over stdio and pooled.** Whatever transport the
  outer agent uses, each foundational server is a child process spoken
  to over stdio; sessions are reused between calls and closed when
  idle, so the gateway never opens a network socket of its own towards
  a sub-server.
- **Four transports, one command line.** stdio for a client that spawns
  the process; streamable HTTP and SSE from the suite's shared
  `_cli`/`_transports` pair, unauthenticated and bound to loopback by
  default; authenticated streamable HTTP in `http/transport.py` for
  shared multi-tenant deployments (ADR 0001).
- **Profiles are data.** The baseline clearing profiles are JSON files
  in `data/`; premium rule packs plug into the same engine through
  `register()` without a code change.
- **Optional extras stay optional.** OpenTelemetry (`[otel]`) is
  imported lazily; the base install does not pull it in.
- **Coverage enforced at 100%** line+branch and docstring
  (`interrogate`); the suite-conformance test pins the invariants every
  repository of the suite shares.

## Extension points

- **Add a tool:** a `@server.tool(...)` function in
  `iso20022_readiness_suite_mcp/server.py` that calls an orchestrator;
  pair it with tests in `tests/test_server.py`, document it in the
  README and update the tool count in `glama.json` and `server.json`.
- **Add a clearing profile:** a JSON file in
  `iso20022_readiness_suite_mcp/data/` (see `docs/profiles.md`), or a
  runtime `register()` call for a rule pack shipped separately.
- **Add a sub-server:** an entry in the command map read by
  `clients/sub_server.py`, and a route in `orchestrators/routing.py`.
- **Add a resource:** `@server.resource("readiness://...")`.
- **Add a prompt:** `@server.prompt()`.

## Where to look first

- Runnable examples: [`examples/`](examples/)
- Decisions: [`docs/adr/`](docs/adr/index.md)
- The meta-client pattern: [`docs/orchestration.md`](docs/orchestration.md)
- Roadmap: [`ROADMAP.md`](ROADMAP.md)
- Release process: [`RELEASING.md`](RELEASING.md)
