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

"""Framework adapters: expose the readiness-suite tools to agent frameworks.

The orchestration server registers its tools (``list_profiles``,
``run_readiness_check``, ``remediate_payload``, ``simulate_bank_response``)
with FastMCP. Agent frameworks such as LangChain, CrewAI and LlamaIndex each
have their own tool object; this module introspects the FastMCP tool registry
and wraps every registered tool into the requested framework's native tool
type, one framework tool per gateway tool.

Some readiness-suite tools are ``async`` and some are synchronous; the
adapters wrap them all the same way -- the framework's tool object receives
the underlying callable (or a thin error-mapping closure over it) exactly as
registered, so the coroutine/plain distinction is preserved end to end.

Each ``as_*_tools`` function pulls its framework in lazily, so importing this
module -- and the base ``iso20022-readiness-suite-mcp`` install -- never
depends on any agent framework. A framework is only needed when its adapter is
actually called; if it is absent the adapter raises :class:`ImportError`
naming the extra to install
(e.g. ``pip install iso20022-readiness-suite-mcp[langchain]``).

The tool metadata (name, description and the JSON ``inputSchema``) and the
underlying callable are read from the FastMCP tool registry via
:func:`_gateway_tools`. The introspected JSON input schema is passed straight
through to each framework's schema argument.
"""

from collections.abc import Callable
from typing import Any

from iso20022_readiness_suite_mcp.server import server


def _gateway_tools() -> list[Any]:
    """Return the gateway's registered FastMCP tools for adapter wrapping.

    Reads the FastMCP tool manager's registry, so each entry carries the
    tool's ``name``, ``description``, JSON input schema (``parameters``) and
    the underlying callable (``fn``).
    """
    return list(server._tool_manager.list_tools())


def _wrap_with_tool_exception(
    fn: Callable[..., Any], tool_exception: type[Exception]
) -> Callable[..., Any]:
    """Wrap a gateway callable so raised errors become ``tool_exception``.

    LangChain signals a recoverable tool failure by raising
    ``ToolException``; the gateway tools normally return an ``{"error": ...}``
    payload rather than raising, but any unexpected error is mapped to the
    framework's convention here.
    """

    def _call(**kwargs: Any) -> Any:
        """Invoke the wrapped tool, mapping failures to ``tool_exception``."""
        try:
            return fn(**kwargs)
        except Exception as exc:
            raise tool_exception(str(exc)) from exc

    return _call


def as_langchain_tools() -> list[Any]:
    """Wrap every gateway tool as a LangChain ``StructuredTool``.

    Returns one :class:`langchain_core.tools.StructuredTool` per registered
    gateway tool, carrying its name, description and JSON input schema; the
    callable is wrapped so raised errors surface as ``ToolException``.

    Raises:
        ImportError: if ``langchain-core`` is not installed
            (``pip install iso20022-readiness-suite-mcp[langchain]``).
    """
    try:
        from langchain_core.tools import StructuredTool, ToolException
    except ImportError as exc:
        raise ImportError(
            "LangChain is not installed. Install it with "
            "`pip install iso20022-readiness-suite-mcp[langchain]`."
        ) from exc

    return [
        StructuredTool.from_function(
            func=_wrap_with_tool_exception(tool.fn, ToolException),
            name=tool.name,
            description=tool.description,
            args_schema=tool.parameters,
        )
        for tool in _gateway_tools()
    ]


def as_crewai_tools() -> list[Any]:
    """Wrap every gateway tool as a CrewAI ``CrewStructuredTool``.

    Returns one ``crewai.tools.CrewStructuredTool`` per registered gateway
    tool, carrying its name, description, JSON input schema and callable.

    Raises:
        ImportError: if CrewAI is not installed
            (``pip install iso20022-readiness-suite-mcp[crewai]``).
    """
    try:
        from crewai.tools import CrewStructuredTool
    except ImportError as exc:
        raise ImportError(
            "CrewAI is not installed. Install it with "
            "`pip install iso20022-readiness-suite-mcp[crewai]`."
        ) from exc

    return [
        CrewStructuredTool.from_function(
            func=tool.fn,
            name=tool.name,
            description=tool.description,
            args_schema=tool.parameters,
        )
        for tool in _gateway_tools()
    ]


def as_llamaindex_tools() -> list[Any]:
    """Wrap every gateway tool as a LlamaIndex ``FunctionTool``.

    Returns one ``llama_index.core.tools.FunctionTool`` per registered gateway
    tool, carrying its name, description, JSON input schema and callable.

    Raises:
        ImportError: if ``llama-index-core`` is not installed
            (``pip install iso20022-readiness-suite-mcp[llamaindex]``).
    """
    try:
        from llama_index.core.tools import FunctionTool
    except ImportError as exc:
        raise ImportError(
            "LlamaIndex is not installed. Install it with "
            "`pip install iso20022-readiness-suite-mcp[llamaindex]`."
        ) from exc

    return [
        FunctionTool.from_defaults(
            fn=tool.fn,
            name=tool.name,
            description=tool.description,
            fn_schema=tool.parameters,
        )
        for tool in _gateway_tools()
    ]
