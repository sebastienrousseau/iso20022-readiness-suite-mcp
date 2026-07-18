# Orchestration & the meta-client pattern

`iso20022-readiness-suite-mcp` is both an MCP **server** (to the outer
agent) and an MCP **client** (to the foundational suite servers). This
"server that is also a client" arrangement is the **meta-client
pattern**: the gateway exposes four high-level tools, and underneath it
spawns the foundational servers over stdio, calls one tool on each, and
composes their results into a single readiness answer.

## The seam

The orchestrators never talk to a concrete transport. They depend only
on a small protocol:

```python
class SubServerInvoker(Protocol):
    async def call(
        self, server: str, tool: str, arguments: Mapping[str, Any]
    ) -> ToolOutcome:
        ...
```

- **In production**, `StdioSubServerInvoker` implements it: for each
  call it spins up the named server over stdio, runs
  `session.initialize()`, calls one tool, and tears the session down.
- **In tests**, a fake implementing the same protocol is injected, so
  100% of the orchestration logic is exercised without spawning a single
  real sub-process.

Every failure is returned as **data**, never raised across the boundary:

| Situation | Outcome |
| --- | --- |
| No launch command configured for the server | `ToolOutcome(ok=False)` with code `RS_SUBSERVER_UNAVAILABLE` |
| Spawn / connection failure (server not installed, crashes on start) | `ToolOutcome(ok=False)` with code `RS_SUBSERVER_UNAVAILABLE` |
| The sub-server itself reports a tool error | `ToolOutcome(ok=False)` with code `RS_SUBSERVER_TOOL_ERROR` |
| Success | `ToolOutcome(ok=True, data=...)` |

The tool the agent called then folds that outcome into a typed response
and, on any failure, returns an `{"error": ...}` payload — the agent
sees a clear message, never a traceback.

## Which tools reach the sub-servers

| Tool | Reaches sub-servers? | Why |
| --- | --- | --- |
| `list_profiles` | No | Reads the bundled clearing-profile data only. |
| `simulate_bank_response` | No | A purely local pacs.002 generator (closed-world). |
| `run_readiness_check` | Yes | Detects the message type, routes to the correct base validator, and lints/scores the result. |
| `remediate_payload` | Yes | Delegates the remediation to `structured-address-fix-mcp`. |

So `list_profiles` and `simulate_bank_response` work with nothing else
installed; `run_readiness_check` and `remediate_payload` need the
relevant foundational server to be resolvable.

## Pointing the gateway at the sub-servers

### Default: zero-install `uvx`

Out of the box, each foundational server is launched with a `uvx`
command, so a single `pip install uv` is enough to make them resolvable
without a separate install step:

| Sub-server | Default launch command |
| --- | --- |
| `iso20022-mcp` | `uvx iso20022-mcp` |
| `camt053-mcp` | `uvx camt053-mcp` |
| `pain001-mcp` | `uvx pain001-mcp` |
| `reconcile-mcp` | `uvx reconcile-mcp` |
| `bankstatementparser-mcp` | `uvx bankstatementparser-mcp` |
| `structured-address-fix-mcp` | `uvx structured-address-fix-mcp` |

`uvx` resolves and caches each server on first use; subsequent calls
reuse the cache. To warm the cache ahead of time (e.g. in a container
build), pre-run the servers once:

```sh
uvx structured-address-fix-mcp --version
uvx camt053-mcp --version
```

### Local console scripts or a pinned virtualenv

The `StdioSubServerInvoker` accepts a `command_map` — a mapping from a
server name to the argv that launches it — so a deployment that embeds
the gateway can substitute the defaults. For example, to launch locally
installed console scripts (pinned in one virtualenv) instead of `uvx`:

```python
from iso20022_readiness_suite_mcp.clients.sub_server import (
    StdioSubServerInvoker,
)

invoker = StdioSubServerInvoker(
    command_map={
        "iso20022-mcp": ["/opt/venvs/suite/bin/iso20022-mcp"],
        "camt053-mcp": ["/opt/venvs/suite/bin/camt053-mcp"],
        "pain001-mcp": ["/opt/venvs/suite/bin/pain001-mcp"],
        "reconcile-mcp": ["/opt/venvs/suite/bin/reconcile-mcp"],
        "bankstatementparser-mcp": ["/opt/venvs/suite/bin/bankstatementparser-mcp"],
        "structured-address-fix-mcp": ["/opt/venvs/suite/bin/structured-address-fix-mcp"],
    }
)
```

Any argv works: a bare console script, `python -m <module>`, a wrapper
script, or a `docker run -i --rm <image>` invocation that launches a
sub-server packaged as a container.

### Remote / containerised sub-servers

The transport is stdio, so a "remote" sub-server is one whose argv is a
thin local launcher that bridges to it — for example a `docker run -i`
against a locally available image, or an SSH/`kubectl exec` wrapper that
forwards stdio to a server running elsewhere. The gateway does not open
network sockets itself; it always speaks stdio to whatever the argv
launches. Keep each launcher fast to start, because the invoker spawns a
fresh session per call.

## Operational notes

- **One process per call.** Each sub-server call is an isolated,
  short-lived session. There is no long-lived pool in v0.0.1; a shared,
  multi-tenant HTTP transport is on the [roadmap](https://github.com/sebastienrousseau/iso20022-readiness-suite-mcp/blob/main/ROADMAP.md).
- **Least privilege.** The gateway runs as the local process owner with
  no network listener; the sub-servers it launches inherit that
  environment. A maliciously configured command map is out of scope (see
  [`SECURITY.md`](https://github.com/sebastienrousseau/iso20022-readiness-suite-mcp/blob/main/SECURITY.md)).
- **Failure is visible.** If a readiness check comes back with a
  `RS_SUBSERVER_UNAVAILABLE` finding, the named sub-server was not
  resolvable — install it or fix its launch command.
