"""Compatibility layer over the ``mcp`` SDK's two supported majors.

``mcp`` 2.0 removed the ``mcp.server.fastmcp`` module: ``FastMCP`` became
``mcp.server.MCPServer`` and ``Context`` moved to ``mcp.server.context``.
Server construction, the ``.tool()`` / ``.resource()`` decorators and
``.run()`` are otherwise identical, so a single indirection covers both.

Import the server class, :data:`Context` and :func:`build_server` from
here rather than from ``mcp`` directly, so there is exactly one place to
update when the SDK moves again.

The two majors also differ in how ``serverInfo.version`` is set: 2.x
takes ``version=`` on the constructor and exposes ``.version`` read-only,
while 1.x has neither and needs the value poked onto the underlying
low-level server. :func:`build_server` and :func:`server_version` hide
that difference.

Only one major can be installed at a time, so whichever branch is not
taken is unreachable and carries ``pragma: no cover``. Both branches are
exercised in CI by running the suite twice — once against the pinned
requirements (2.x) and once against the floor of the declared range.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "MCP_MAJOR",
    "Context",
    "MCPServer",
    "build_server",
    "server_version",
]


def _resolve() -> tuple[Any, Any, int]:
    """Return ``(server_class, context_class, major)`` for the installed SDK."""
    import mcp.server as _mcp_server

    server_cls = getattr(_mcp_server, "MCPServer", None)
    if server_cls is not None:  # mcp >= 2
        from mcp.server.context import Context

        return server_cls, Context, 2

    # mcp 1.x. Imported dynamically on purpose: a static
    # ``from mcp.server import fastmcp`` cannot type-check while 2.x is
    # installed, because the module no longer exists there. Going
    # through the module object also avoids rebinding ``Context``, which
    # a second ``from … import Context`` would do.
    import importlib  # pragma: no cover

    fastmcp = importlib.import_module("mcp.server.fastmcp")  # pragma: no cover
    return fastmcp.FastMCP, fastmcp.Context, 1  # pragma: no cover


MCPServer, Context, MCP_MAJOR = _resolve()


def build_server(name: str, version: str) -> Any:
    """Construct the MCP server, reporting ``version`` in ``serverInfo``."""
    if MCP_MAJOR >= 2:
        return MCPServer(name, version=version)

    server = MCPServer(name)  # pragma: no cover  (FastMCP on 1.x)
    server._mcp_server.version = version  # pragma: no cover
    return server  # pragma: no cover


def server_version(server: Any) -> str:
    """Read back the version a server reports, across both majors."""
    version = getattr(server, "version", None)
    if version:
        return str(version)
    return str(server._mcp_server.version)  # pragma: no cover
