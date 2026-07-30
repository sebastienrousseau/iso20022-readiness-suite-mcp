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

"""Tests for the optional OpenTelemetry tracing module.

Spans are captured with an in-memory exporter so assertions never touch the
network, and the missing-``[otel]``-extra path is exercised by forcing the
lazy ``opentelemetry`` import to fail.
"""

from __future__ import annotations

import builtins
from collections.abc import Iterator

import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from iso20022_readiness_suite_mcp import tracing


@pytest.fixture(autouse=True)
def _reset_tracing() -> Iterator[None]:
    """Reset module-level tracing state before and after each test."""
    tracing._tracer = None
    tracing._provider = None
    yield
    provider = tracing._provider
    if provider is not None:
        provider.shutdown()
    tracing._tracer = None
    tracing._provider = None


def _capture() -> InMemorySpanExporter:
    """Attach an in-memory exporter to the live provider and return it."""
    exporter = InMemorySpanExporter()
    tracing.provider().add_span_processor(SimpleSpanProcessor(exporter))
    return exporter


def test_is_enabled_reflects_state() -> None:
    """``is_enabled`` is False before init and True afterwards."""
    assert tracing.is_enabled() is False
    assert tracing.init_tracing() is True
    assert tracing.is_enabled() is True


def test_init_without_endpoint_creates_provider() -> None:
    """Init with no endpoint installs a provider but attaches no exporter."""
    assert tracing.init_tracing(service_name="svc-under-test") is True
    assert tracing._provider is not None
    assert tracing._tracer is not None


def test_init_with_endpoint_argument() -> None:
    """An explicit endpoint wires up the OTLP batch exporter branch."""
    assert (
        tracing.init_tracing(endpoint="http://localhost:4318/v1/traces")
        is True
    )
    assert tracing.is_enabled() is True


def test_init_with_endpoint_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A falsy endpoint falls back to OTEL_EXPORTER_OTLP_ENDPOINT."""
    monkeypatch.setenv(
        tracing._ENDPOINT_ENV, "http://localhost:4318/v1/traces"
    )
    assert tracing.init_tracing() is True
    assert tracing.is_enabled() is True


def test_init_returns_false_when_extra_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing ``[otel]`` extra degrades init to a graceful no-op."""
    real_import = builtins.__import__

    def _fail(name: str, *args: object, **kwargs: object) -> object:
        """Raise ImportError for any opentelemetry import."""
        if name.startswith("opentelemetry"):
            raise ImportError(f"no module named {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fail)
    assert tracing.init_tracing() is False
    assert tracing.is_enabled() is False


def test_trace_span_is_noop_when_uninitialised() -> None:
    """``trace_span`` yields None and emits nothing when not initialised."""
    with tracing.trace_span("noop") as span:
        assert span is None


def test_trace_span_emits_span() -> None:
    """An initialised ``trace_span`` records a span with the given name."""
    assert tracing.init_tracing() is True
    exporter = _capture()
    with tracing.trace_span("unit-op") as span:
        assert span is not None
    spans = exporter.get_finished_spans()
    assert [s.name for s in spans] == ["unit-op"]


def test_trace_span_records_exception() -> None:
    """A raised exception is recorded on the span with an error status."""
    from opentelemetry.trace import StatusCode

    assert tracing.init_tracing() is True
    exporter = _capture()
    # try/except (not pytest.raises) so the post-block assertions are plainly
    # reachable to static analysis while still proving the exception re-raises.
    raised: ValueError | None = None
    try:
        with tracing.trace_span("failing-op"):
            raise ValueError("boom")
    except ValueError as exc:
        raised = exc
    assert raised is not None and str(raised) == "boom"
    (span,) = exporter.get_finished_spans()
    assert span.name == "failing-op"
    assert span.status.status_code is StatusCode.ERROR
    assert span.events
    assert span.events[0].name == "exception"


def test_traced_tool_sync() -> None:
    """The decorator spans a synchronous callable and preserves its result."""
    assert tracing.init_tracing() is True
    exporter = _capture()

    @tracing.traced_tool("sync-tool")
    def add(a: int, b: int) -> int:
        return a + b

    assert add(2, 3) == 5
    assert [s.name for s in exporter.get_finished_spans()] == ["sync-tool"]


@pytest.mark.asyncio
async def test_traced_tool_async() -> None:
    """The decorator spans an async callable and preserves its result."""
    assert tracing.init_tracing() is True
    exporter = _capture()

    @tracing.traced_tool("async-tool")
    async def mul(a: int, b: int) -> int:
        return a * b

    assert await mul(4, 5) == 20
    assert [s.name for s in exporter.get_finished_spans()] == ["async-tool"]


@pytest.mark.asyncio
async def test_traced_tool_noop_passthrough() -> None:
    """When uninitialised the decorator passes calls through unchanged."""

    @tracing.traced_tool("sync-noop")
    def echo(value: str) -> str:
        return value

    @tracing.traced_tool("async-noop")
    async def aecho(value: str) -> str:
        return value

    assert echo("x") == "x"
    assert await aecho("y") == "y"
    assert tracing.is_enabled() is False
