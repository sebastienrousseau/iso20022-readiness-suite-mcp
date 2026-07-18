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
) -> None:
    """Patch ``stdio_client`` and ``ClientSession`` with in-memory fakes."""
    monkeypatch.setattr(
        mcp.client.stdio, "stdio_client", lambda params: _FakeStdioCM()
    )
    monkeypatch.setattr(mcp, "ClientSession", _make_fake_session(result))


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
