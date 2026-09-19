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
:class:`StdioSubServerInvoker` is the production implementation: it launches
each underlying server over stdio on first use and keeps that session open
for later calls, so the cost of starting a Python process (about two
seconds through ``uvx``) is paid once per server rather than once per tool
call. A session that fails is dropped and the next call starts a fresh one.

Every failure — a missing server, a spawn error, a tool error — is returned
as a :class:`ToolOutcome`, never raised across the caller boundary, upholding
the data-not-tracebacks paradigm.
"""

from __future__ import annotations

import asyncio
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


class _Request:
    """One queued tool call: what to run and where to put the answer."""

    def __init__(self, tool: str, arguments: dict[str, Any]) -> None:
        """Record the call and create the future its result lands in."""
        self.tool = tool
        self.arguments = arguments
        self.done: asyncio.Future[Any] = (
            asyncio.get_running_loop().create_future()
        )


class _SubServerSession:
    """One long-lived stdio session with an underlying server.

    The MCP client transport is built from ``anyio`` task groups, which
    must be entered and left by the same task. A tool call on this server
    can be served by any task, so the session is owned by a dedicated
    task that opens the transport, serves requests from a queue until it
    is closed or idles out, and tears the transport down itself.
    """

    def __init__(self, argv: list[str], idle_seconds: float) -> None:
        """Remember how to launch the server and how long to keep it."""
        self._argv = argv
        self._idle_seconds = idle_seconds
        self._queue: asyncio.Queue[_Request | None] = asyncio.Queue()
        self._ready: asyncio.Future[None] = (
            asyncio.get_running_loop().create_future()
        )
        self._task = asyncio.create_task(self._serve())

    async def call(self, tool: str, arguments: dict[str, Any]) -> Any:
        """Run one tool call on the owned session and return its result.

        Raises whatever the transport or the server raised, so the caller
        can drop the session and report the failure as data.
        """
        await self._ready
        if self.closed:
            raise RuntimeError("sub-server session closed")
        request = _Request(tool, arguments)
        await self._queue.put(request)
        if self.closed:
            # The owner left between the check and the put; nobody will
            # drain the queue now, so do it here (this request included).
            self._fail_pending(RuntimeError("sub-server session closed"))
        return await request.done

    @property
    def closed(self) -> bool:
        """Whether the owning task has finished, for any reason."""
        return self._task.done()

    async def aclose(self) -> None:
        """Ask the owning task to leave the transport, and wait for it."""
        await self._queue.put(None)
        await asyncio.gather(self._task, return_exceptions=True)

    async def _serve(self) -> None:
        """Own the transport for the session's whole life."""
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=self._argv[0], args=list(self._argv[1:])
        )
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._ready.set_result(None)
                    await self._pump(session)
        except BaseException as exc:  # noqa: BLE001 - relayed to waiters
            if not self._ready.done():
                self._ready.set_exception(exc)
            self._fail_pending(exc)
            if isinstance(exc, asyncio.CancelledError):
                raise
        else:
            # Left on purpose (closed or idle): anything queued meanwhile
            # must not wait forever for an owner that is gone.
            self._fail_pending(RuntimeError("sub-server session closed"))

    async def _pump(self, session: Any) -> None:
        """Serve queued requests until closed or idle for too long."""
        while True:
            request = await self._next()
            if request is None:
                return
            try:
                result = await session.call_tool(
                    request.tool, request.arguments
                )
            except Exception as exc:  # noqa: BLE001 - handed to the caller
                request.done.set_exception(exc)
                return
            request.done.set_result(result)

    async def _next(self) -> _Request | None:
        """Wait for the next request; ``None`` means stop (told to, or idle).

        Not ``asyncio.wait_for``: on Python 3.10 and 3.11 a cancellation
        that lands while it is waiting can surface as ``TimeoutError``,
        which would turn "stop now" into "idle, leave quietly" and hide
        the cancellation from the owner.
        """
        getter = asyncio.ensure_future(self._queue.get())
        try:
            done, _ = await asyncio.wait({getter}, timeout=self._idle_seconds)
        except BaseException:
            if getter.done() and not getter.cancelled():
                # It dequeued something in the same tick; hand it back so
                # the owner's drain fails it rather than losing it.
                self._queue.put_nowait(getter.result())
            else:
                getter.cancel()
            raise
        if not done:
            getter.cancel()
            return None
        return getter.result()

    def _fail_pending(self, exc: BaseException) -> None:
        """Fail every request still queued when the session went away."""
        while not self._queue.empty():
            request = self._queue.get_nowait()
            if request is not None and not request.done.done():
                request.done.set_exception(
                    exc
                    if isinstance(exc, Exception)
                    else RuntimeError("sub-server session closed")
                )


class StdioSubServerInvoker:
    """Invoke sub-server tools over stdio sessions that stay open.

    The first call to a server launches it and keeps the session; later
    calls reuse it. A session that fails, or that sits idle for
    ``idle_seconds``, is dropped and the next call starts a fresh one.
    Call :meth:`aclose` to stop every launched server.

    Args:
        command_map: Maps a server name to the argv that launches it.
            Defaults to :data:`DEFAULT_COMMAND_MAP`.
        idle_seconds: How long an unused session stays open. Bounds how
            long a spare process outlives the last call that needed it.
    """

    def __init__(
        self,
        command_map: Mapping[str, list[str]] | None = None,
        idle_seconds: float = 300.0,
    ) -> None:
        """Store the server-launch command map and the idle bound."""
        self._command_map: dict[str, list[str]] = dict(
            command_map if command_map is not None else DEFAULT_COMMAND_MAP
        )
        self._idle_seconds = idle_seconds
        self._sessions: dict[str, _SubServerSession] = {}

    async def call(
        self, server: str, tool: str, arguments: Mapping[str, Any]
    ) -> ToolOutcome:
        """Call ``tool`` on ``server``, launching it first if needed.

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
            self._sessions.pop(server, None)
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

    async def aclose(self) -> None:
        """Stop every launched server."""
        sessions = list(self._sessions.values())
        self._sessions.clear()
        for session in sessions:
            await session.aclose()

    def _session(self, server: str, argv: list[str]) -> _SubServerSession:
        """Return the live session for ``server``, starting one if needed."""
        session = self._sessions.get(server)
        if session is None or session.closed:
            session = _SubServerSession(argv, self._idle_seconds)
            self._sessions[server] = session
        return session

    async def _invoke(
        self,
        argv: list[str],
        server: str,
        tool: str,
        arguments: Mapping[str, Any],
    ) -> ToolOutcome:
        """Run one tool call on the server's session."""
        result = await self._session(server, argv).call(tool, dict(arguments))
        data = _decode_content(list(result.content))
        if getattr(result, "isError", getattr(result, "is_error", False)):
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
