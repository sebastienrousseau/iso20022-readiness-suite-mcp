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

"""Optional OpenTelemetry tracing for the readiness-suite MCP server.

Tracing is an opt-in feature guarded by the ``[otel]`` extra. When the extra
is not installed, or tracing has simply not been initialised, every helper in
this module degrades to a zero-overhead no-op: :func:`init_tracing` returns
``False`` and :func:`trace_span` / :func:`traced_tool` pass the wrapped
operation straight through without emitting a span.

Typical wiring::

    from iso20022_readiness_suite_mcp import tracing

    tracing.init_tracing(endpoint="http://localhost:4318/v1/traces")

    @tracing.traced_tool("my_tool")
    def my_tool(...):
        ...

Nothing here ever changes a tool's return value; the only observable effect of
enabling tracing is that spans are exported.
"""

from __future__ import annotations

import functools
import inspect
import os
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from typing import Any, TypeVar, cast

__all__ = [
    "init_tracing",
    "is_enabled",
    "trace_span",
    "traced_tool",
]

#: Default value for the OTLP endpoint environment variable.
_ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_ENDPOINT"

# Module-level state. ``_tracer`` is the live OpenTelemetry ``Tracer`` once
# :func:`init_tracing` has succeeded, and ``None`` otherwise (the no-op state).
# ``_provider`` is retained so callers/tests can attach extra span processors.
_tracer: Any = None
_provider: Any = None

F = TypeVar("F", bound=Callable[..., Any])


def is_enabled() -> bool:
    """Return ``True`` when tracing has been initialised and is active."""
    return _tracer is not None


def init_tracing(
    endpoint: str | None = None,
    service_name: str = "iso20022-readiness-suite-mcp",
) -> bool:
    """Initialise OpenTelemetry tracing for the server.

    Lazily imports the OpenTelemetry SDK so the dependency stays optional.

    Args:
        endpoint: OTLP/HTTP traces endpoint. When falsy, the
            ``OTEL_EXPORTER_OTLP_ENDPOINT`` environment variable is consulted.
            When neither is set, a provider is still created but no exporter is
            attached (spans are produced but not shipped anywhere).
        service_name: Value recorded as the ``service.name`` resource
            attribute on every emitted span.

    Returns:
        ``True`` once a tracer has been installed; ``False`` when the ``[otel]``
        extra is not installed (in which case tracing stays a no-op).
    """
    global _tracer, _provider
    try:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
    except ImportError:
        return False

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    endpoint = endpoint or os.environ.get(_ENDPOINT_ENV)
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
        )

    _provider = provider
    _tracer = provider.get_tracer(service_name)
    return True


@contextmanager
def trace_span(name: str) -> Iterator[Any]:
    """Span ``name`` for the duration of the ``with`` block.

    Records any exception raised inside the block on the span and marks the
    span status as an error before re-raising, so failures remain visible in
    the trace. When tracing is uninitialised this is a no-op that yields
    ``None`` and adds no overhead.

    Args:
        name: The span name.

    Yields:
        The active span, or ``None`` when tracing is not active.
    """
    tracer = _tracer
    if tracer is None:
        yield None
        return

    from opentelemetry.trace import Status, StatusCode

    with tracer.start_as_current_span(name) as span:
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


def traced_tool(name: str) -> Callable[[F], F]:
    """Decorate a tool callable so each invocation opens a :func:`trace_span`.

    Works for both synchronous and ``async`` functions; the coroutine is
    awaited inside the span so the span covers the whole call. When tracing is
    inactive the wrapper adds a no-op context manager and does not alter the
    wrapped callable's return value.

    Args:
        name: The span name to use for each invocation.

    Returns:
        A decorator preserving the wrapped callable's signature.
    """

    def decorator(func: F) -> F:
        """Wrap ``func`` in a span-opening sync or async shim."""
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                """Await ``func`` inside a span."""
                with trace_span(name):
                    return await cast(Callable[..., Awaitable[Any]], func)(
                        *args, **kwargs
                    )

            return cast(F, async_wrapper)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            """Call ``func`` inside a span."""
            with trace_span(name):
                return func(*args, **kwargs)

        return cast(F, sync_wrapper)

    return decorator
