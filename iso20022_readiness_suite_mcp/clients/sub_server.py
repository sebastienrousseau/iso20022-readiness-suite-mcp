# Copyright (C) 2023-2026 Sebastien Rousseau.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""The meta-client seam: invoke tools on the underlying MCP servers.

This module implements the "server that is also a client" half of the
orchestration pattern. An orchestrator depends only on the
:class:`SubServerInvoker` protocol, so tests inject a fake and 100 % of the
orchestration logic is exercised without spawning real sub-processes. The
:class:`StdioSubServerInvoker` is the production implementation: it spins up
an underlying server over stdio, calls one tool, and tears the session down.

Every failure — a missing server, a spawn error, a tool error — is returned
as a :class:`ToolOutcome`, never raised across the caller boundary, upholding
the data-not-tracebacks paradigm.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from iso20022_readiness_suite_mcp.errors import ErrorDetail

#: Default command used to launch each underlying server (zero-install uvx).
#: Override per deployment via ``StdioSubServerInvoker(command_map=...)``.
DEFAULT_COMMAND_MAP: dict[str, list[str]] = {
    "iso20022-mcp": ["uvx", "iso20022-mcp"],
    "camt053-mcp": ["uvx", "camt053-mcp"],
    "pain001-mcp": ["uvx", "pain001-mcp"],
    "reconcile-mcp": ["uvx", "reconcile-mcp"],
    "bankstatementparser-mcp": ["uvx", "bankstatementparser-mcp"],
    "structured-address-fix-mcp": ["uvx", "structured-address-fix-mcp"],
}


class ToolOutcome(BaseModel):
    """The result of a single sub-server tool invocation."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    data: Any = None
    error: ErrorDetail | None = None


@runtime_checkable
class SubServerInvoker(Protocol):
    """Contract for invoking a tool on an underlying MCP server."""

    async def call(
        self, server: str, tool: str, arguments: Mapping[str, Any]
    ) -> ToolOutcome:
        """Invoke ``tool`` on ``server`` and return its outcome as data."""
        ...


def _decode_content(content: list[Any]) -> Any:
    """Decode an MCP tool result's content list into plain Python data.

    Text items are JSON-decoded when possible, otherwise returned verbatim;
    a single item is unwrapped, multiple items are returned as a list.
    """
    decoded: list[Any] = []
    for item in content:
        text = getattr(item, "text", None)
        if text is None:
            decoded.append(getattr(item, "data", repr(item)))
            continue
        try:
            decoded.append(json.loads(text))
        except (ValueError, TypeError):
            decoded.append(text)
    if len(decoded) == 1:
        return decoded[0]
    return decoded


class StdioSubServerInvoker:
    """Invoke sub-server tools by spawning each server over stdio.

    Args:
        command_map: Maps a server name to the argv that launches it.
            Defaults to :data:`DEFAULT_COMMAND_MAP`.
    """

    def __init__(
        self, command_map: Mapping[str, list[str]] | None = None
    ) -> None:
        """Store the server-launch command map."""
        self._command_map: dict[str, list[str]] = dict(
            command_map if command_map is not None else DEFAULT_COMMAND_MAP
        )

    async def call(
        self, server: str, tool: str, arguments: Mapping[str, Any]
    ) -> ToolOutcome:
        """Spawn ``server``, call ``tool``, and return its outcome.

        A missing server mapping, a spawn/connection failure, or a tool-level
        error each yield a non-``ok`` :class:`ToolOutcome` with an
        :class:`ErrorDetail`; nothing propagates as an exception.
        """
        argv = self._command_map.get(server)
        if argv is None:
            return ToolOutcome(
                ok=False,
                error=ErrorDetail(
                    code="RS_SUBSERVER_UNAVAILABLE",
                    locator=f"{server}:{tool}",
                    explanation=f"No launch command configured for {server!r}.",
                ),
            )
        try:
            return await self._invoke(argv, server, tool, arguments)
        except Exception as exc:  # noqa: BLE001 - boundary: never leak traces
            return ToolOutcome(
                ok=False,
                error=ErrorDetail(
                    code="RS_SUBSERVER_UNAVAILABLE",
                    locator=f"{server}:{tool}",
                    explanation=(
                        f"Failed to invoke {tool!r} on {server!r}: {exc}"
                    ),
                ),
            )

    async def _invoke(
        self,
        argv: list[str],
        server: str,
        tool: str,
        arguments: Mapping[str, Any],
    ) -> ToolOutcome:
        """Run one tool call inside a fresh stdio client session."""
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(command=argv[0], args=list(argv[1:]))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool, dict(arguments))
        data = _decode_content(list(result.content))
        if getattr(result, "isError", False):
            return ToolOutcome(
                ok=False,
                error=ErrorDetail(
                    code="RS_SUBSERVER_TOOL_ERROR",
                    locator=f"{server}:{tool}",
                    explanation=f"{server} reported a tool error.",
                    context={"result": data},
                ),
            )
        return ToolOutcome(ok=True, data=data)
