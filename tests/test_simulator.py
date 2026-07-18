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

"""Bank-response simulation: pacs.002 generation and typed error paths."""

from __future__ import annotations

import pytest

from iso20022_readiness_suite_mcp.models import SimulateResponseRequest
from iso20022_readiness_suite_mcp.orchestrators import simulator
from tests.conftest import PAIN_001

_NO_MSGID = (
    '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.09">'
    "<CstmrCdtTrfInitn><MsgId></MsgId></CstmrCdtTrfInitn></Document>"
)


def test_simulate_accept() -> None:
    """An ACCP request emits a pacs.002 carrying the group status."""
    req = SimulateResponseRequest(
        inbound_payload=PAIN_001, desired_behavior="ACCP"
    )
    resp = simulator.simulate_bank_response(req)
    assert resp.error is None
    assert resp.status == "ACCP"
    assert resp.generated_response_type == "pacs.002.001.10"
    assert "<GrpSts>ACCP</GrpSts>" in resp.response_payload
    assert "<MsgId>SIM-MSG-1</MsgId>" in resp.response_payload
    assert "pain.001.001.09" in resp.response_payload


def test_simulate_pending() -> None:
    """A PDNG request emits a pacs.002 with a pending group status."""
    req = SimulateResponseRequest(
        inbound_payload=PAIN_001, desired_behavior="PDNG"
    )
    resp = simulator.simulate_bank_response(req)
    assert resp.status == "PDNG"
    assert "<GrpSts>PDNG</GrpSts>" in resp.response_payload
    assert "<StsRsnInf>" not in resp.response_payload  # no reason block


def test_simulate_reject_with_reason() -> None:
    """An RJCT request with a reason code embeds the reason block."""
    req = SimulateResponseRequest(
        inbound_payload=PAIN_001,
        desired_behavior="RJCT",
        reason_code="AM04",
    )
    resp = simulator.simulate_bank_response(req)
    assert resp.error is None
    assert "<GrpSts>RJCT</GrpSts>" in resp.response_payload
    assert "<Cd>AM04</Cd>" in resp.response_payload


def test_simulate_reject_without_reason_errors() -> None:
    """An RJCT with no reason code is a typed invalid-input error."""
    req = SimulateResponseRequest(
        inbound_payload=PAIN_001, desired_behavior="RJCT"
    )
    resp = simulator.simulate_bank_response(req)
    assert resp.error is not None
    assert resp.error.code == "RS_INVALID_INPUT"
    assert resp.error.locator == "/reason_code"


def test_simulate_unparseable_inbound_errors() -> None:
    """Non-XML inbound content yields a typed invalid-input error."""
    req = SimulateResponseRequest(
        inbound_payload="not xml at all", desired_behavior="ACCP"
    )
    resp = simulator.simulate_bank_response(req)
    assert resp.error is not None
    assert resp.error.code == "RS_INVALID_INPUT"
    assert "not parseable" in resp.error.explanation


def test_simulate_missing_msgid_and_type() -> None:
    """An empty MsgId falls back to UNKNOWN; unknown namespace to 'unknown'."""
    req = SimulateResponseRequest(
        inbound_payload="<Document><MsgId></MsgId></Document>",
        desired_behavior="ACCP",
    )
    resp = simulator.simulate_bank_response(req)
    assert "<MsgId>SIM-UNKNOWN</MsgId>" in resp.response_payload
    assert "<OrgnlMsgNmId>unknown</OrgnlMsgNmId>" in resp.response_payload


def test_simulate_empty_msgid_element() -> None:
    """A present-but-empty MsgId element is treated as absent (UNKNOWN)."""
    req = SimulateResponseRequest(
        inbound_payload=_NO_MSGID, desired_behavior="ACCP"
    )
    resp = simulator.simulate_bank_response(req)
    assert "<MsgId>SIM-UNKNOWN</MsgId>" in resp.response_payload


def test_simulate_generic_exception_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unexpected error after validation surfaces as an RS_ERROR detail."""

    def boom(*args: object, **kwargs: object) -> str:
        """Raise to simulate an unexpected build failure."""
        raise RuntimeError("build failed")

    monkeypatch.setattr(simulator, "_build_pacs002", boom)
    req = SimulateResponseRequest(
        inbound_payload=PAIN_001, desired_behavior="ACCP"
    )
    resp = simulator.simulate_bank_response(req)
    assert resp.error is not None
    assert resp.error.code == "RS_ERROR"
    assert "build failed" in resp.error.explanation


def test_first_text_direct() -> None:
    """``_first_text`` returns a stripped hit and empty string on a miss."""
    from defusedxml.ElementTree import fromstring

    root = fromstring("<a><b>  hi  </b></a>")
    assert simulator._first_text(root, "b") == "hi"
    assert simulator._first_text(root, "z") == ""
