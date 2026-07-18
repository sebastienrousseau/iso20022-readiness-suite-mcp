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

"""The readiness and remediation orchestrators.

Every path uses the fake invoker from ``conftest`` so the orchestration
logic is proven without spawning a real sub-server.
"""

from __future__ import annotations

import pytest

from iso20022_readiness_suite_mcp.clients.sub_server import ToolOutcome
from iso20022_readiness_suite_mcp.errors import (
    ErrorDetail,
    SubServerUnavailableError,
)
from iso20022_readiness_suite_mcp.models import (
    ReadinessCheckRequest,
    RemediateRequest,
)
from iso20022_readiness_suite_mcp.orchestrators import readiness
from iso20022_readiness_suite_mcp.orchestrators.routing import route_for
from iso20022_readiness_suite_mcp.policies.engine import ProfileEngine
from tests.conftest import (
    CAMT_053,
    NON_ISO,
    PAIN_001,
    FakeInvoker,
    RaisingInvoker,
)


@pytest.fixture
def engine() -> ProfileEngine:
    """The bundled clearing-profile engine."""
    return ProfileEngine.from_bundled()


# --------------------------------------------------------------------------
# run_readiness_check
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_readiness_pain001_cbpr(
    valid_invoker: FakeInvoker, engine: ProfileEngine
) -> None:
    """A valid pain.001 against CBPR+ scores 70 with two profile findings."""
    req = ReadinessCheckRequest(
        payload_content=PAIN_001, target_profile="CBPR+"
    )
    resp = await readiness.run_readiness_check(req, valid_invoker, engine)
    assert resp.message_type == "pain.001.001.09"
    assert resp.is_valid is True
    assert valid_invoker.calls[0][:2] == (
        "pain001-mcp",
        "validate_xml_against_schema",
    )
    codes = {f.code for f in resp.profile_findings}
    assert codes == {"CBPR_MISSING_COUNTRY", "CBPR_MISSING_TOWN"}
    assert resp.readiness_score == 70


@pytest.mark.asyncio
async def test_readiness_routes_camt(
    valid_invoker: FakeInvoker, engine: ProfileEngine
) -> None:
    """A camt.05x payload routes to the camt053 statement validator."""
    req = ReadinessCheckRequest(payload_content=CAMT_053)
    await readiness.run_readiness_check(req, valid_invoker, engine)
    assert valid_invoker.calls[0][:2] == (
        "camt053-mcp",
        "validate_statement",
    )


@pytest.mark.asyncio
async def test_readiness_unrecognized_message(
    valid_invoker: FakeInvoker, engine: ProfileEngine
) -> None:
    """A non-ISO payload short-circuits to an unrecognized-message error."""
    req = ReadinessCheckRequest(payload_content=NON_ISO)
    resp = await readiness.run_readiness_check(req, valid_invoker, engine)
    assert resp.is_valid is False
    assert resp.structural_errors[0].code == "RS_UNRECOGNIZED_MESSAGE"
    assert resp.readiness_score == 0
    assert valid_invoker.calls == []  # no sub-server call was attempted


@pytest.mark.asyncio
async def test_readiness_unknown_profile_degrades(
    valid_invoker: FakeInvoker, engine: ProfileEngine
) -> None:
    """An unknown target profile degrades to a single profile finding."""
    req = ReadinessCheckRequest(
        payload_content=PAIN_001, target_profile="NoSuchProfile"
    )
    resp = await readiness.run_readiness_check(req, valid_invoker, engine)
    assert resp.is_valid is True
    assert [f.code for f in resp.profile_findings] == ["RS_UNKNOWN_PROFILE"]


@pytest.mark.asyncio
async def test_readiness_generic_exception_boundary(
    engine: ProfileEngine,
) -> None:
    """A non-ReadinessError from the invoker surfaces as an RS_ERROR detail."""
    invoker = RaisingInvoker(RuntimeError("kaboom"))
    req = ReadinessCheckRequest(payload_content=PAIN_001)
    resp = await readiness.run_readiness_check(req, invoker, engine)
    assert resp.is_valid is False
    assert resp.error is not None
    assert resp.error.code == "RS_ERROR"
    assert "kaboom" in resp.error.explanation


@pytest.mark.asyncio
async def test_readiness_readiness_error_boundary(
    engine: ProfileEngine,
) -> None:
    """A ReadinessError from the invoker preserves its own code."""
    invoker = RaisingInvoker(SubServerUnavailableError("down"))
    req = ReadinessCheckRequest(payload_content=PAIN_001)
    resp = await readiness.run_readiness_check(req, invoker, engine)
    assert resp.error is not None
    assert resp.error.code == "RS_SUBSERVER_UNAVAILABLE"


# --------------------------------------------------------------------------
# _interpret_validation
# --------------------------------------------------------------------------
def _pain_route():
    """Return the pain.001 validation route (for locator assertions)."""
    return route_for("pain.001.001.09")


def test_interpret_not_ok_returns_error() -> None:
    """A non-ok outcome surfaces its own error as the structural error."""
    err = ErrorDetail(code="RS_SUBSERVER_TOOL_ERROR", explanation="boom")
    outcome = ToolOutcome(ok=False, error=err)
    assert readiness._interpret_validation(outcome, _pain_route()) == [err]


def test_interpret_error_key() -> None:
    """A ``{'error': ...}`` result maps to a single structural error."""
    outcome = ToolOutcome(ok=True, data={"error": "bad tag"})
    result = readiness._interpret_validation(outcome, _pain_route())
    assert len(result) == 1
    assert result[0].code == "RS_STRUCTURAL_INVALID"
    assert result[0].explanation == "bad tag"


def test_interpret_valid_false_with_errors() -> None:
    """``valid: False`` with an errors list yields one detail per error."""
    outcome = ToolOutcome(
        ok=True, data={"valid": False, "errors": ["e1", "e2"]}
    )
    result = readiness._interpret_validation(outcome, _pain_route())
    assert [r.explanation for r in result] == ["e1", "e2"]


def test_interpret_is_valid_false_reason_fallback() -> None:
    """``is_valid: False`` with no errors falls back to the reason."""
    outcome = ToolOutcome(
        ok=True, data={"is_valid": False, "reason": "schema mismatch"}
    )
    result = readiness._interpret_validation(outcome, _pain_route())
    assert [r.explanation for r in result] == ["schema mismatch"]


def test_interpret_is_valid_false_default_invalid() -> None:
    """``is_valid: False`` with neither errors nor reason yields 'invalid'."""
    outcome = ToolOutcome(ok=True, data={"is_valid": False})
    result = readiness._interpret_validation(outcome, _pain_route())
    assert [r.explanation for r in result] == ["invalid"]


def test_interpret_valid_true() -> None:
    """A ``valid: True`` result has no structural errors."""
    outcome = ToolOutcome(ok=True, data={"valid": True})
    assert readiness._interpret_validation(outcome, _pain_route()) == []


def test_interpret_non_dict_data() -> None:
    """Non-dict data (e.g. ``None``) yields no structural errors."""
    outcome = ToolOutcome(ok=True, data=None)
    assert readiness._interpret_validation(outcome, _pain_route()) == []


# --------------------------------------------------------------------------
# remediate_payload / _build_remediation
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_remediate_applied() -> None:
    """A changed patched_xml with suggestions marks remediation applied."""
    data = {
        "patched_xml": "<Document>patched</Document>",
        "suggestions": [
            {
                "explanation": "Added Ctry",
                "residual_findings": [
                    {"code": "SAF005", "location": "/x", "message": "m"}
                ],
            },
            {"residual_findings": []},  # no explanation -> skipped in log
        ],
    }
    invoker = FakeInvoker(ToolOutcome(ok=True, data=data))
    req = RemediateRequest(
        payload_content="<Document>orig</Document>", target_profile="CBPR+"
    )
    resp = await readiness.remediate_payload(req, invoker)
    assert resp.remediation_applied is True
    assert resp.mutated_payload == "<Document>patched</Document>"
    assert resp.fixes_log == ("Added Ctry",)
    assert resp.residual_findings[0].code == "SAF005"
    assert resp.residual_findings[0].locator == "/x"
    assert invoker.calls[0][:2] == (
        "structured-address-fix-mcp",
        "remediate_message",
    )


@pytest.mark.asyncio
async def test_remediate_not_ok() -> None:
    """A non-ok remediate outcome returns the original with the error."""
    err = ErrorDetail(code="RS_SUBSERVER_UNAVAILABLE", explanation="down")
    invoker = FakeInvoker(ToolOutcome(ok=False, error=err))
    req = RemediateRequest(payload_content="<Document/>")
    resp = await readiness.remediate_payload(req, invoker)
    assert resp.remediation_applied is False
    assert resp.mutated_payload == "<Document/>"
    assert resp.error == err


@pytest.mark.asyncio
async def test_remediate_no_change() -> None:
    """An unchanged patched_xml (or None) leaves remediation unapplied."""
    invoker = FakeInvoker(
        ToolOutcome(ok=True, data={"patched_xml": "<Document/>"})
    )
    req = RemediateRequest(payload_content="<Document/>")
    resp = await readiness.remediate_payload(req, invoker)
    assert resp.remediation_applied is False
    assert resp.mutated_payload == "<Document/>"


@pytest.mark.asyncio
async def test_remediate_patched_none() -> None:
    """A result with no patched_xml is treated as no remediation."""
    invoker = FakeInvoker(ToolOutcome(ok=True, data={"suggestions": []}))
    req = RemediateRequest(payload_content="<Document/>")
    resp = await readiness.remediate_payload(req, invoker)
    assert resp.remediation_applied is False


@pytest.mark.asyncio
async def test_remediate_non_dict_data() -> None:
    """Non-dict remediation data degrades to no-op, not a crash."""
    invoker = FakeInvoker(ToolOutcome(ok=True, data="unexpected"))
    req = RemediateRequest(payload_content="<Document/>")
    resp = await readiness.remediate_payload(req, invoker)
    assert resp.remediation_applied is False
    assert resp.mutated_payload == "<Document/>"


@pytest.mark.asyncio
async def test_remediate_generic_exception_boundary() -> None:
    """A non-ReadinessError during remediation surfaces as RS_ERROR."""
    invoker = RaisingInvoker(RuntimeError("nope"))
    req = RemediateRequest(payload_content="<Document/>")
    resp = await readiness.remediate_payload(req, invoker)
    assert resp.remediation_applied is False
    assert resp.error is not None
    assert resp.error.code == "RS_ERROR"


@pytest.mark.asyncio
async def test_remediate_default_policy_for_unknown_profile() -> None:
    """An unmapped profile falls back to the cbpr-2026 address policy."""
    invoker = FakeInvoker(ToolOutcome(ok=True, data={"patched_xml": None}))
    req = RemediateRequest(
        payload_content="<Document/>", target_profile="Mystery"
    )
    await readiness.remediate_payload(req, invoker)
    assert invoker.calls[0][2]["policy_id"] == "cbpr-2026"


@pytest.mark.asyncio
async def test_remediate_sepa_policy_mapping() -> None:
    """The SEPA_Instant profile maps to the sepa address policy."""
    invoker = FakeInvoker(ToolOutcome(ok=True, data={"patched_xml": None}))
    req = RemediateRequest(
        payload_content="<Document/>", target_profile="SEPA_Instant"
    )
    await readiness.remediate_payload(req, invoker)
    assert invoker.calls[0][2]["policy_id"] == "sepa"


# --------------------------------------------------------------------------
# _as_detail
# --------------------------------------------------------------------------
def test_as_detail_readiness_error() -> None:
    """A ReadinessError renders via its own ``to_detail``."""
    detail = readiness._as_detail(SubServerUnavailableError("x"))
    assert detail.code == "RS_SUBSERVER_UNAVAILABLE"


def test_as_detail_generic() -> None:
    """A plain exception renders as an RS_ERROR detail."""
    detail = readiness._as_detail(ValueError("boom"))
    assert detail.code == "RS_ERROR"
    assert "boom" in detail.explanation
