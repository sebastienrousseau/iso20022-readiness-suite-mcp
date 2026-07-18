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

"""Readiness and remediation orchestrators.

These compose the underlying MCP servers into higher-order workflows: a raw
payload is detected, structurally validated by the correct base server,
linted against a clearing profile, and scored; remediation is delegated to
``structured-address-fix-mcp``. Every orchestrator returns a typed response
and never raises across the tool boundary.
"""

from __future__ import annotations

from typing import Any

from iso20022_readiness_suite_mcp.clients.sub_server import (
    SubServerInvoker,
    ToolOutcome,
)
from iso20022_readiness_suite_mcp.errors import (
    ErrorDetail,
    ReadinessError,
    UnknownProfileError,
)
from iso20022_readiness_suite_mcp.models import (
    ReadinessCheckRequest,
    ReadinessCheckResponse,
    RemediateRequest,
    RemediateResponse,
)
from iso20022_readiness_suite_mcp.orchestrators.routing import (
    ValidationRoute,
    detect_message_type,
    route_for,
)
from iso20022_readiness_suite_mcp.policies.engine import ProfileEngine
from iso20022_readiness_suite_mcp.reports import compiler

#: Maps a readiness-suite profile to a structured-address-fix policy id.
_ADDRESS_POLICY = {
    "CBPR+": "cbpr-2026",
    "FedNow": "cbpr-2026",
    "SEPA_Instant": "sepa",
    "Generic": "generic-structured",
}


def _interpret_validation(
    outcome: ToolOutcome, route: ValidationRoute
) -> list[ErrorDetail]:
    """Turn a base-validator outcome into a list of structural errors."""
    if not outcome.ok:
        assert outcome.error is not None  # ok is False => error is set
        return [outcome.error]
    data = outcome.data
    locator = f"{route.server}:{route.tool}"
    if isinstance(data, dict):
        if data.get("error") is not None:
            return [
                ErrorDetail(
                    code="RS_STRUCTURAL_INVALID",
                    locator=locator,
                    explanation=str(data["error"]),
                )
            ]
        if data.get("valid") is False or data.get("is_valid") is False:
            raw = data.get("errors") or [data.get("reason", "invalid")]
            return [
                ErrorDetail(
                    code="RS_STRUCTURAL_INVALID",
                    locator=locator,
                    explanation=str(item),
                )
                for item in raw
            ]
    return []


async def run_readiness_check(
    req: ReadinessCheckRequest,
    invoker: SubServerInvoker,
    engine: ProfileEngine,
) -> ReadinessCheckResponse:
    """Detect, validate, profile-lint, and score a payload."""
    try:
        message_type = detect_message_type(req.payload_content)
        if message_type is None:
            detail = ErrorDetail(
                code="RS_UNRECOGNIZED_MESSAGE",
                explanation="Payload carries no ISO 20022 namespace.",
            )
            return ReadinessCheckResponse(
                is_valid=False,
                structural_errors=(detail,),
                readiness_score=0,
            )

        route = route_for(message_type)
        outcome = await invoker.call(
            route.server,
            route.tool,
            route.build_args(req.payload_content, message_type),
        )
        structural = _interpret_validation(outcome, route)
        profile = _apply_profile(engine, req.target_profile, req)
        score = compiler.compute_score(structural, profile)
        return ReadinessCheckResponse(
            is_valid=not structural,
            message_type=message_type,
            structural_errors=tuple(structural),
            profile_findings=tuple(profile),
            readiness_score=score,
        )
    except Exception as exc:  # noqa: BLE001 - boundary: return data, not trace
        return ReadinessCheckResponse(is_valid=False, error=_as_detail(exc))


def _apply_profile(
    engine: ProfileEngine, profile_id: str, req: ReadinessCheckRequest
) -> list[ErrorDetail]:
    """Apply a clearing profile, degrading gracefully on an unknown id."""
    try:
        return engine.apply(profile_id, req.payload_content)
    except UnknownProfileError as exc:
        return [exc.to_detail()]


async def remediate_payload(
    req: RemediateRequest, invoker: SubServerInvoker
) -> RemediateResponse:
    """Delegate automated remediation to structured-address-fix-mcp."""
    try:
        policy = _ADDRESS_POLICY.get(req.target_profile, "cbpr-2026")
        outcome = await invoker.call(
            "structured-address-fix-mcp",
            "remediate_message",
            {
                "xml": req.payload_content,
                "policy_id": policy,
                "apply": True,
            },
        )
        if not outcome.ok:
            assert outcome.error is not None
            return RemediateResponse(
                remediation_applied=False,
                mutated_payload=req.payload_content,
                error=outcome.error,
            )
        return _build_remediation(outcome.data, req.payload_content)
    except Exception as exc:  # noqa: BLE001 - boundary
        return RemediateResponse(
            remediation_applied=False,
            mutated_payload=req.payload_content,
            error=_as_detail(exc),
        )


def _build_remediation(data: Any, original: str) -> RemediateResponse:
    """Assemble a remediation response from a remediate_message result."""
    patched = data.get("patched_xml") if isinstance(data, dict) else None
    suggestions = data.get("suggestions", []) if isinstance(data, dict) else []
    fixes: list[str] = []
    residual: list[ErrorDetail] = []
    for suggestion in suggestions:
        explanation = suggestion.get("explanation")
        if explanation:
            fixes.append(explanation)
        for finding in suggestion.get("residual_findings", []):
            residual.append(
                ErrorDetail(
                    code=str(finding.get("code", "RESIDUAL")),
                    locator=str(finding.get("location", "/")),
                    explanation=str(finding.get("message", "")),
                )
            )
    applied = bool(patched) and patched != original
    return RemediateResponse(
        remediation_applied=applied,
        mutated_payload=patched if applied else original,
        fixes_log=tuple(fixes),
        residual_findings=tuple(residual),
    )


def _as_detail(exc: Exception) -> ErrorDetail:
    """Render any exception as a serializable :class:`ErrorDetail`."""
    if isinstance(exc, ReadinessError):
        return exc.to_detail()
    return ErrorDetail(
        code="RS_ERROR", explanation=f"Unexpected orchestration error: {exc}"
    )
