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

"""Request/response schemas: extra-field rejection and round-tripping."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from iso20022_readiness_suite_mcp.errors import ErrorDetail
from iso20022_readiness_suite_mcp.models import (
    ClearingProfile,
    ProfileRule,
    ReadinessCheckRequest,
    ReadinessCheckResponse,
    RemediateRequest,
    RemediateResponse,
    SimulateResponseRequest,
    SimulateResponseResponse,
)


@pytest.mark.parametrize(
    ("cls", "kwargs"),
    [
        (ReadinessCheckRequest, {"payload_content": "<x/>"}),
        (RemediateRequest, {"payload_content": "<x/>"}),
        (
            SimulateResponseRequest,
            {"inbound_payload": "<x/>", "desired_behavior": "ACCP"},
        ),
    ],
)
def test_requests_forbid_extra_fields(
    cls: type, kwargs: dict[str, object]
) -> None:
    """Every request model rejects unexpected keys (``extra='forbid'``)."""
    cls(**kwargs)  # baseline is accepted
    with pytest.raises(ValidationError):
        cls(**kwargs, unexpected="nope")


def test_readiness_response_round_trip() -> None:
    """A readiness response survives ``model_dump`` / re-validation."""
    detail = ErrorDetail(code="C", locator="/a", explanation="e")
    resp = ReadinessCheckResponse(
        is_valid=False,
        message_type="pain.001.001.09",
        structural_errors=(detail,),
        profile_findings=(detail,),
        readiness_score=42,
    )
    again = ReadinessCheckResponse.model_validate(resp.model_dump(mode="json"))
    assert again == resp


def test_remediate_response_round_trip() -> None:
    """A remediation response round-trips through JSON."""
    resp = RemediateResponse(
        remediation_applied=True,
        mutated_payload="<y/>",
        fixes_log=("did a thing",),
    )
    again = RemediateResponse.model_validate(resp.model_dump(mode="json"))
    assert again == resp


def test_simulate_response_round_trip() -> None:
    """A simulate response round-trips through JSON."""
    resp = SimulateResponseResponse(
        status="ACCP",
        generated_response_type="pacs.002.001.10",
        response_payload="<Document/>",
    )
    again = SimulateResponseResponse.model_validate(
        resp.model_dump(mode="json")
    )
    assert again == resp


def test_clearing_profile_round_trip() -> None:
    """A clearing profile with a nested rule round-trips through JSON."""
    profile = ClearingProfile(
        profile_id="X",
        market_practice="Demo",
        supported_messages=("pain.001",),
        custom_rules=(
            ProfileRule(
                rule_id="r1",
                description="d",
                locator="Ctry",
                assertion="required",
                error_code="X_MISSING",
            ),
        ),
    )
    again = ClearingProfile.model_validate(profile.model_dump(mode="json"))
    assert again == profile
    assert again.custom_rules[0].severity == "error"


def test_simulate_request_rejects_bad_behavior() -> None:
    """``desired_behavior`` is constrained to the ACCP/RJCT/PDNG literal."""
    with pytest.raises(ValidationError):
        SimulateResponseRequest(
            inbound_payload="<x/>", desired_behavior="MAYBE"
        )
