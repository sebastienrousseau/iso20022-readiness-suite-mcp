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

"""Pydantic request/response schemas for the orchestration tools.

All tool inputs and outputs are typed models: the MCP surface never accepts
or emits an untyped ``dict``. Inbound payloads are passed as raw string
content (``payload_content``), never as server filesystem paths.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from iso20022_readiness_suite_mcp.errors import ErrorDetail


class ReadinessCheckRequest(BaseModel):
    """Input for :func:`run_readiness_check`."""

    model_config = ConfigDict(extra="forbid")

    payload_content: str = Field(description="Raw ISO 20022 payload text.")
    filename_hint: str | None = Field(
        default=None, description="Optional original filename, for routing."
    )
    target_profile: str = Field(
        default="Generic",
        description="Clearing profile to lint against (e.g. 'CBPR+', "
        "'FedNow', 'SEPA_Instant').",
    )


class ReadinessCheckResponse(BaseModel):
    """Aggregated readiness outcome for a payload."""

    model_config = ConfigDict(frozen=True)

    is_valid: bool
    message_type: str = ""
    structural_errors: tuple[ErrorDetail, ...] = ()
    profile_findings: tuple[ErrorDetail, ...] = ()
    readiness_score: int = Field(default=0, ge=0, le=100)
    error: ErrorDetail | None = None


class RemediateRequest(BaseModel):
    """Input for :func:`remediate_payload`."""

    model_config = ConfigDict(extra="forbid")

    payload_content: str
    error_context: tuple[ErrorDetail, ...] = ()
    target_profile: str = "Generic"


class RemediateResponse(BaseModel):
    """Outcome of a remediation attempt."""

    model_config = ConfigDict(frozen=True)

    remediation_applied: bool
    mutated_payload: str = ""
    fixes_log: tuple[str, ...] = ()
    residual_findings: tuple[ErrorDetail, ...] = ()
    error: ErrorDetail | None = None


class SimulateResponseRequest(BaseModel):
    """Input for :func:`simulate_bank_response`."""

    model_config = ConfigDict(extra="forbid")

    inbound_payload: str
    desired_behavior: Literal["ACCP", "RJCT", "PDNG"]
    reason_code: str | None = Field(
        default=None,
        description="ISO external status reason, e.g. 'AM04' "
        "(insufficient funds). Required for RJCT.",
    )


class SimulateResponseResponse(BaseModel):
    """A simulated bank status response."""

    model_config = ConfigDict(frozen=True)

    status: str = ""
    generated_response_type: str = ""
    response_payload: str = ""
    error: ErrorDetail | None = None


class ClearingProfile(BaseModel):
    """A market-practice / clearing-scheme rule set beyond XSD checks."""

    model_config = ConfigDict(frozen=True)

    profile_id: str
    market_practice: str
    supported_messages: tuple[str, ...] = ()
    custom_rules: tuple[ProfileRule, ...] = ()


class ProfileRule(BaseModel):
    """A single declarative profile assertion."""

    model_config = ConfigDict(frozen=True)

    rule_id: str
    description: str
    #: An XPath-like locator the rule inspects.
    locator: str
    #: A simple declarative condition (evaluated by the policy engine).
    assertion: str
    error_code: str
    severity: Literal["info", "warning", "error"] = "error"


ClearingProfile.model_rebuild()
