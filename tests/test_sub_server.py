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

"""The stdio meta-client: decoding, routing, and failure-as-data.

The ``_invoke`` happy/error paths are exercised against async
context-manager fakes patched in for ``stdio_client`` / ``ClientSession``,
so no real sub-process is ever spawned.
"""

from __future__ import annotations

import asyncio
from typing import Any

import mcp
import mcp.client.stdio
import pytest

from iso20022_readiness_suite_mcp.clients.sub_server import (
    DEFAULT_COMMAND_MAP,
    StdioSubServerInvoker,
    SubServerInvoker,
    ToolOutcome,
    _decode_content,
)


class _TextItem:
    """A content item exposing a ``.text`` attribute (like MCP TextContent)."""

    def __init__(self, text: str) -> None:
        """Store the item's text."""
        self.text = text


class _DataItem:
    """A content item with no ``.text`` but a structured ``.data`` payload."""

    text = None

    def __init__(self, data: Any) -> None:
        """Store the item's structured data."""
        self.data = data


def test_decode_content_json_text() -> None:
    """JSON-decodable text is parsed into Python data."""
    assert _decode_content([_TextItem('{"a": 1}')]) == {"a": 1}


def test_decode_content_plain_text() -> None:
    """Non-JSON text is returned verbatim."""
    assert _decode_content([_TextItem("hello")]) == "hello"


def test_decode_content_data_item() -> None:
    """An item with no ``.text`` falls back to its ``.data`` attribute."""
    assert _decode_content([_DataItem({"k": "v"})]) == {"k": "v"}


def test_decode_content_multiple_items() -> None:
    """Multiple items are returned as a list; a single item is unwrapped."""
    out = _decode_content([_TextItem("a"), _TextItem('{"b": 2}')])
    assert out == ["a", {"b": 2}]


def test_default_command_map_covers_known_servers() -> None:
    """The default map launches each foundational server via uvx."""
    assert DEFAULT_COMMAND_MAP["camt053-mcp"] == ["uvx", "camt053-mcp"]


def test_invoker_satisfies_protocol() -> None:
    """The production invoker satisfies the :class:`SubServerInvoker`."""
    assert isinstance(StdioSubServerInvoker(), SubServerInvoker)


def test_custom_command_map_is_copied() -> None:
    """A supplied command map is copied, not aliased."""
    supplied = {"x-mcp": ["run", "x"]}
    inv = StdioSubServerInvoker(command_map=supplied)
    supplied["x-mcp"].append("mutated")
    assert inv._command_map["x-mcp"] == ["run", "x", "mutated"]  # list aliased
    # The dict itself is a distinct object.
    assert inv._command_map is not supplied


@pytest.mark.asyncio
async def test_call_unknown_server_no_spawn() -> None:
    """Calling an unmapped server fails as data, without spawning anything."""
    inv = StdioSubServerInvoker(command_map={})
    out = await inv.call("nope-mcp", "do", {})
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "RS_SUBSERVER_UNAVAILABLE"
    assert out.error.locator == "nope-mcp:do"


@pytest.mark.asyncio
async def test_call_invoke_raises_is_captured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A spawn/connection failure inside ``_invoke`` is captured as data."""
    inv = StdioSubServerInvoker()

    async def boom(*args: Any, **kwargs: Any) -> ToolOutcome:
        """Raise to simulate a spawn/connection failure."""
        raise RuntimeError("spawn failed")

    monkeypatch.setattr(inv, "_invoke", boom)
    out = await inv.call("iso20022-mcp", "parse", {})
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "RS_SUBSERVER_UNAVAILABLE"
    assert "spawn failed" in out.error.explanation


class _FakeStdioCM:
    """An async CM yielding a ``(read, write)`` pair, like ``stdio_client``."""

    async def __aenter__(self) -> tuple[str, str]:
        return ("read", "write")

    async def __aexit__(self, *exc: Any) -> bool:
        return False


class _FakeResult:
    """A tool-call result with ``.content`` and an ``.isError`` flag."""

    def __init__(self, content: list[Any], is_error: bool) -> None:
        """Store the result content list and error flag."""
        self.content = content
        self.isError = is_error


def _make_fake_session(result: _FakeResult) -> type:
    """Build a fake ``ClientSession`` class returning ``result``."""

    class _FakeSession:
        """An async-CM stand-in for ``mcp.ClientSession``."""

        def __init__(self, read: str, write: str) -> None:
            """Store the read/write stream stand-ins."""
            self._read = read
            self._write = write

        async def __aenter__(self) -> _FakeSession:
            return self

        async def __aexit__(self, *exc: Any) -> bool:
            return False

        async def initialize(self) -> None:
            """Pretend to initialise the session (no-op)."""
            return None

        async def call_tool(
            self, tool: str, args: dict[str, Any]
        ) -> _FakeResult:
            """Return the pre-canned tool result."""
            return result

    return _FakeSession


def _patch_transport(
    monkeypatch: pytest.MonkeyPatch, result: _FakeResult
) -> list[Any]:
    """Patch ``stdio_client`` and ``ClientSession`` with in-memory fakes.

    Returns the list of launch parameters, one entry per server start, so
    a test can assert how many processes the invoker would have spawned.
    """
    launches: list[Any] = []

    def fake_stdio_client(params: Any) -> _FakeStdioCM:
        launches.append(params)
        return _FakeStdioCM()

    monkeypatch.setattr(mcp.client.stdio, "stdio_client", fake_stdio_client)
    monkeypatch.setattr(mcp, "ClientSession", _make_fake_session(result))
    return launches


@pytest.mark.asyncio
async def test_invoke_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """A successful tool call decodes its content into ``ok`` data."""
    result = _FakeResult([_TextItem('{"valid": true}')], is_error=False)
    _patch_transport(monkeypatch, result)
    inv = StdioSubServerInvoker()
    out = await inv.call("iso20022-mcp", "parse", {"xml": "<x/>"})
    assert out.ok is True
    assert out.data == {"valid": True}
    assert out.error is None


@pytest.mark.asyncio
async def test_invoke_tool_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A tool-level error becomes a non-ok outcome carrying the result."""
    result = _FakeResult([_TextItem("boom detail")], is_error=True)
    _patch_transport(monkeypatch, result)
    inv = StdioSubServerInvoker()
    out = await inv.call("pain001-mcp", "validate_xml_against_schema", {})
    assert out.ok is False
    assert out.error is not None
    assert out.error.code == "RS_SUBSERVER_TOOL_ERROR"
    assert out.error.locator == "pain001-mcp:validate_xml_against_schema"
    assert out.error.context == {"result": "boom detail"}


@pytest.mark.asyncio
async def test_session_is_reused_across_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeat calls to one server ride the session the first call opened.

    Starting a sub-server costs seconds; the pool exists so an agent that
    calls ``remediate_payload`` five times pays that once, not five times.
    """
    result = _FakeResult([_TextItem('{"ok": 1}')], is_error=False)
    launches = _patch_transport(monkeypatch, result)
    inv = StdioSubServerInvoker()
    for _ in range(3):
        out = await inv.call("iso20022-mcp", "parse", {})
        assert out.ok is True
    out = await inv.call("pain001-mcp", "validate", {})
    assert out.ok is True
    assert len(launches) == 2, "one launch per distinct server"
    await inv.aclose()
    assert not inv._sessions


@pytest.mark.asyncio
async def test_failed_session_is_dropped_and_relaunched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transport failure is reported as data and the session forgotten."""
    launches: list[Any] = []
    attempts = {"n": 0}

    class _BrokenOnce:
        async def __aenter__(self) -> tuple[str, str]:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise OSError("spawn failed")
            return ("read", "write")

        async def __aexit__(self, *exc: Any) -> bool:
            return False

    def fake_stdio_client(params: Any) -> _BrokenOnce:
        launches.append(params)
        return _BrokenOnce()

    result = _FakeResult([_TextItem("fine")], is_error=False)
    monkeypatch.setattr(mcp.client.stdio, "stdio_client", fake_stdio_client)
    monkeypatch.setattr(mcp, "ClientSession", _make_fake_session(result))
    inv = StdioSubServerInvoker()
    first = await inv.call("camt053-mcp", "parse", {})
    assert first.ok is False
    assert first.error is not None
    assert first.error.code == "RS_SUBSERVER_UNAVAILABLE"
    assert "spawn failed" in first.error.explanation
    second = await inv.call("camt053-mcp", "parse", {})
    assert second.ok is True
    assert second.data == "fine"
    assert len(launches) == 2
    await inv.aclose()


@pytest.mark.asyncio
async def test_idle_session_closes_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unused session leaves after ``idle_seconds`` and is replaced."""
    result = _FakeResult([_TextItem("x")], is_error=False)
    launches = _patch_transport(monkeypatch, result)
    inv = StdioSubServerInvoker(idle_seconds=0.01)
    assert (await inv.call("iso20022-mcp", "parse", {})).ok is True
    session = inv._sessions["iso20022-mcp"]
    await asyncio.wait_for(session._task, 1.0)
    assert session.closed
    assert (await inv.call("iso20022-mcp", "parse", {})).ok is True
    assert len(launches) == 2
    await inv.aclose()


@pytest.mark.asyncio
async def test_tool_exception_fails_that_call_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exception from ``call_tool`` is data for that call; the next
    call gets a fresh session."""
    calls = {"n": 0}

    class _Session:
        def __init__(self, read: str, write: str) -> None:
            pass

        async def __aenter__(self) -> _Session:
            return self

        async def __aexit__(self, *exc: Any) -> bool:
            return False

        async def initialize(self) -> None:
            return None

        async def call_tool(self, tool: str, args: dict[str, Any]) -> Any:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("pipe broke")
            return _FakeResult([_TextItem("ok")], is_error=False)

    monkeypatch.setattr(
        mcp.client.stdio, "stdio_client", lambda params: _FakeStdioCM()
    )
    monkeypatch.setattr(mcp, "ClientSession", _Session)
    inv = StdioSubServerInvoker()
    first = await inv.call("iso20022-mcp", "parse", {})
    assert first.ok is False
    assert first.error is not None
    assert "pipe broke" in first.error.explanation
    second = await inv.call("iso20022-mcp", "parse", {})
    assert second.ok is True
    await inv.aclose()


@pytest.mark.asyncio
async def test_queued_call_fails_when_the_owner_leaves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A call queued behind one that broke the session is failed, not left
    waiting forever, and the invoker relaunches for the call after it."""
    gate = asyncio.Event()
    calls = {"n": 0}

    class _Session:
        def __init__(self, read: str, write: str) -> None:
            pass

        async def __aenter__(self) -> _Session:
            return self

        async def __aexit__(self, *exc: Any) -> bool:
            return False

        async def initialize(self) -> None:
            return None

        async def call_tool(self, tool: str, args: dict[str, Any]) -> Any:
            calls["n"] += 1
            if calls["n"] == 1:
                await gate.wait()
                raise RuntimeError("pipe broke")
            return _FakeResult([_TextItem("ok")], is_error=False)

    monkeypatch.setattr(
        mcp.client.stdio, "stdio_client", lambda params: _FakeStdioCM()
    )
    monkeypatch.setattr(mcp, "ClientSession", _Session)
    inv = StdioSubServerInvoker()
    first = asyncio.create_task(inv.call("iso20022-mcp", "parse", {}))
    await asyncio.sleep(0)  # let the first call reach call_tool
    second = asyncio.create_task(inv.call("iso20022-mcp", "parse", {}))
    await asyncio.sleep(0)  # and the second sit in the queue
    gate.set()
    outcomes = await asyncio.gather(first, second)
    # Which of the two reached the sub-server first depends on task
    # scheduling; what matters is that one carries the tool's failure and
    # the other is told the session went away, and neither hangs.
    assert all(o.ok is False for o in outcomes)
    reasons = sorted(o.error.explanation for o in outcomes)  # type: ignore[union-attr]
    assert any("pipe broke" in r for r in reasons)
    assert any("session closed" in r for r in reasons)
    assert (await inv.call("iso20022-mcp", "parse", {})).ok is True
    await inv.aclose()


@pytest.mark.asyncio
async def test_cancelled_owner_fails_pending_and_closed_session_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancelling the owning task fails what was queued; a later call on
    that session is refused rather than queued."""
    from iso20022_readiness_suite_mcp.clients.sub_server import (
        _Request,
        _SubServerSession,
    )

    result = _FakeResult([_TextItem("x")], is_error=False)
    _patch_transport(monkeypatch, result)
    session = _SubServerSession(["fake"], idle_seconds=60)
    await session._ready
    pending = _Request("parse", {})
    session._queue.put_nowait(pending)
    session._task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await session._task
    with pytest.raises(RuntimeError, match="session closed"):
        await pending.done
    with pytest.raises(RuntimeError, match="session closed"):
        await session.call("parse", {})


@pytest.mark.asyncio
async def test_call_racing_a_closing_owner_is_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A request put on the queue just as the owner leaves is drained by
    the caller itself instead of waiting on nobody."""
    from iso20022_readiness_suite_mcp.clients.sub_server import (
        _SubServerSession,
    )

    result = _FakeResult([_TextItem("x")], is_error=False)
    _patch_transport(monkeypatch, result)
    session = _SubServerSession(["fake"], idle_seconds=60)
    await session._ready
    # Make the owner finish right after the caller's first "closed" check.
    real_put = session._queue.put

    async def put_then_close(item: Any) -> None:
        # The owner sees the stop signal first, leaves, and only then does
        # the caller's request land on the queue.
        await real_put(None)
        await real_put(item)
        await real_put(None)  # a second stop signal is skipped, not failed
        await asyncio.gather(session._task, return_exceptions=True)

    monkeypatch.setattr(session._queue, "put", put_then_close)
    with pytest.raises(RuntimeError, match="session closed"):
        await session.call("parse", {})


@pytest.mark.asyncio
async def test_cancelled_before_ready_fails_the_waiting_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancelling the owner while the transport is still opening fails the
    call that was waiting for it with a plain error, not a cancellation."""
    from iso20022_readiness_suite_mcp.clients.sub_server import (
        _SubServerSession,
    )

    class _NeverOpens:
        async def __aenter__(self) -> tuple[str, str]:
            await asyncio.Event().wait()
            return ("read", "write")  # pragma: no cover - never reached

        async def __aexit__(self, *exc: Any) -> bool:
            return False

    monkeypatch.setattr(
        mcp.client.stdio, "stdio_client", lambda params: _NeverOpens()
    )
    session = _SubServerSession(["fake"], idle_seconds=60)
    waiting = asyncio.create_task(session.call("parse", {}))
    await asyncio.sleep(0.01)
    session._task.cancel()
    with pytest.raises(RuntimeError, match="session closed"):
        await waiting
    assert session.closed


@pytest.mark.asyncio
async def test_teardown_error_after_ready_fails_what_was_queued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An error while the transport closes is relayed to a request that
    landed on the queue after the stop signal."""
    from iso20022_readiness_suite_mcp.clients.sub_server import (
        _Request,
        _SubServerSession,
    )

    class _Session:
        def __init__(self, read: str, write: str) -> None:
            pass

        async def __aenter__(self) -> _Session:
            return self

        async def __aexit__(self, *exc: Any) -> bool:
            raise RuntimeError("teardown failed")

        async def initialize(self) -> None:
            return None

        async def call_tool(
            self, tool: str, args: dict[str, Any]
        ) -> Any:  # pragma: no cover - never called
            raise AssertionError

    monkeypatch.setattr(
        mcp.client.stdio, "stdio_client", lambda params: _FakeStdioCM()
    )
    monkeypatch.setattr(mcp, "ClientSession", _Session)
    session = _SubServerSession(["fake"], idle_seconds=60)
    await session._ready
    late = _Request("parse", {})
    session._queue.put_nowait(None)
    session._queue.put_nowait(late)
    await session._task
    with pytest.raises(RuntimeError, match="teardown failed"):
        await late.done
