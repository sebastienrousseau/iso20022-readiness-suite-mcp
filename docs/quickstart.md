# Quickstart

A 10-minute install → MCP client config → first conversation tutorial
for `iso20022-readiness-suite-mcp`, the orchestration gateway of the
ISO 20022 MCP Suite.

## 1. Install

`iso20022-readiness-suite-mcp` runs on macOS, Linux, and Windows and
requires Python 3.10+. It pulls in the MCP SDK, `pydantic`, and
`defusedxml` automatically.

```sh
python -m pip install iso20022-readiness-suite-mcp
```

Verify:

```sh
python -c "import iso20022_readiness_suite_mcp; print(iso20022_readiness_suite_mcp.__version__)"
```

Two of the four tools (`run_readiness_check`, `remediate_payload`) reach
the foundational suite servers, which the gateway launches with `uvx`.
Install [`uv`](https://docs.astral.sh/uv/) so those spawns resolve
zero-install:

```sh
python -m pip install uv        # provides the `uvx` launcher
```

`list_profiles` and `simulate_bank_response` are fully local and work
without any of this.

## 2. Launch the server

The package installs an `iso20022-readiness-suite-mcp` console entry
point that starts the server over stdio (FastMCP's default transport):

```sh
iso20022-readiness-suite-mcp
```

The command speaks MCP on stdin/stdout — it is meant to be launched by
an MCP client, not used interactively. (`iso20022-readiness-suite-mcp
--version` prints the version and exits.)

## 3. Register it with your MCP client

### Claude Desktop

Add an entry to `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "iso20022-readiness-suite": { "command": "iso20022-readiness-suite-mcp" }
  }
}
```

Restart Claude Desktop. The 4 tools are now available in any chat.

### Other clients (Cursor, Continue, generic stdio MCP clients)

Point the client at the `iso20022-readiness-suite-mcp` command. The
server speaks standard MCP — no custom transport, no auth. If the entry
point is not on the client's `PATH` (GUI apps often have a minimal
`PATH`), use the absolute path from `which iso20022-readiness-suite-mcp`
in the `command` field.

## 4. First conversation

Drop an ISO 20022 payload into a chat and ask the agent to score its
readiness against a clearing profile and fix it:

> Here is a pacs.008 message. Run a readiness check against the CBPR+
> profile, tell me the score and which rules fail, and if I confirm,
> remediate the payload and show me the fixes.

A typical flow: the agent calls `list_profiles` to discover the target
profiles, `run_readiness_check` to detect / validate / lint / score the
payload, and — on your confirmation — `remediate_payload` to apply the
automated fixes. To rehearse the bank side, it calls
`simulate_bank_response` to emit a pacs.002 ACCP / RJCT / PDNG status
report.

## 5. Use in-process (no MCP client needed)

To prototype or write integration tests, call the tools through the
FastMCP instance directly. The two local tools need no sub-servers:

```python
import asyncio

from iso20022_readiness_suite_mcp import server


async def main() -> None:
    result = await server.server.call_tool("list_profiles", {})
    content = result[0] if isinstance(result, tuple) else result
    print(content[0].text)  # -> [{"profile_id": "CBPR+", ...}, ...]


asyncio.run(main())
```

## 6. The 4 tools at a glance

| Tool | What it does | Sub-servers? |
| --- | --- | --- |
| `list_profiles` | List the clearing profiles (CBPR+, SEPA_Instant, FedNow, Generic) and their rules | No (local) |
| `run_readiness_check` | Detect, validate, profile-lint, and score a payload against a profile | Yes |
| `remediate_payload` | Apply automated remediation (e.g. Nov 2026 structured addresses) | Yes |
| `simulate_bank_response` | Emit a pacs.002 mocking an ACCP / RJCT / PDNG bank response | No (local) |

`run_readiness_check` and `remediate_payload` take an optional
`target_profile` (defaults to `Generic` and `CBPR+` respectively);
`simulate_bank_response` requires a `reason_code` when
`desired_behavior` is `RJCT`.

## 7. Next steps

- Read [`orchestration.md`](orchestration.md) for the meta-client
  pattern and how to point the gateway at local or remote sub-servers.
- Read [`profiles.md`](profiles.md) for the clearing profiles and how
  premium rule packs plug in.
- Browse the full [tool catalog](https://github.com/sebastienrousseau/iso20022-readiness-suite-mcp/blob/main/README.md#tools).

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `command not found: iso20022-readiness-suite-mcp` | Install went to a venv that isn't on PATH | Re-install in your active env, or invoke `python -m iso20022_readiness_suite_mcp.server` |
| MCP client doesn't see the tools | Wrong path in client config | Use an absolute path: `which iso20022-readiness-suite-mcp` → paste into the client `command` |
| `run_readiness_check` returns an `{"error": ...}` about a sub-server | The foundational server isn't resolvable | Install `uv` (for `uvx`), or override the command map to point at a locally installed server (see [`orchestration.md`](orchestration.md)) |
| `simulate_bank_response` rejects the call | `RJCT` was requested without a `reason_code` | Pass a `reason_code` (e.g. `AM04`) when `desired_behavior` is `RJCT` |
