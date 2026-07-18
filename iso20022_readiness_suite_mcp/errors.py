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

"""Error taxonomy for the readiness suite.

Every orchestration failure is expressed as *data*, never a traceback across
the protocol wire (the "data-not-tracebacks" paradigm). :class:`ErrorDetail`
is the serializable shape returned inside tool payloads; the exception
hierarchy is used internally and always caught at the tool boundary.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    """A serializable, human-readable error returned inside a tool payload."""

    model_config = ConfigDict(frozen=True)

    code: str = Field(description="Stable machine-readable error code.")
    locator: str = Field(
        default="/",
        description="Where the error occurred (a JSON pointer, XPath, or "
        "'server:tool' for a sub-server failure).",
    )
    explanation: str = Field(description="Plain-language explanation.")
    context: dict[str, Any] = Field(default_factory=dict)


class ReadinessError(Exception):
    """Base class for every internal readiness-suite error."""

    code: str = "RS_ERROR"

    def __init__(
        self,
        explanation: str,
        *,
        locator: str = "/",
        context: dict[str, Any] | None = None,
    ) -> None:
        """Store the explanation, locator, and structured context."""
        super().__init__(explanation)
        self.explanation = explanation
        self.locator = locator
        self.context = context or {}

    def to_detail(self) -> ErrorDetail:
        """Render this error as a serializable :class:`ErrorDetail`."""
        return ErrorDetail(
            code=self.code,
            locator=self.locator,
            explanation=self.explanation,
            context=self.context,
        )


class InvalidInputError(ReadinessError):
    """The caller supplied malformed or unsafe input."""

    code = "RS_INVALID_INPUT"


class UnsafePathError(InvalidInputError):
    """A supplied path escaped the permitted sandbox."""

    code = "RS_UNSAFE_PATH"


class SubServerUnavailableError(ReadinessError):
    """An underlying MCP server could not be reached or spawned."""

    code = "RS_SUBSERVER_UNAVAILABLE"


class SubServerToolError(ReadinessError):
    """An underlying MCP server returned an error for a tool call."""

    code = "RS_SUBSERVER_TOOL_ERROR"


class UnknownProfileError(ReadinessError):
    """The requested clearing profile is not registered."""

    code = "RS_UNKNOWN_PROFILE"


class RemediationError(ReadinessError):
    """Remediation could not be applied."""

    code = "RS_REMEDIATION_FAILED"
