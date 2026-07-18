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

"""Bank-response simulation.

A workflow-virtualization helper: given an inbound initiation payload and a
desired behaviour, it emits a well-formed ``pacs.002`` status report that
cross-references the original message. Generation is deterministic and local
(no sub-server), so it is a fast, offline mock for integration testing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from xml.sax.saxutils import escape

from defusedxml.ElementTree import fromstring

from iso20022_readiness_suite_mcp.errors import ErrorDetail, InvalidInputError
from iso20022_readiness_suite_mcp.models import (
    SimulateResponseRequest,
    SimulateResponseResponse,
)
from iso20022_readiness_suite_mcp.orchestrators.routing import (
    detect_message_type,
)

_RESPONSE_TYPE = "pacs.002.001.10"


def _first_text(root: Any, element: str) -> str:
    """Return the first descendant's text for ``element``, or empty string."""
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] == element and node.text:
            return str(node.text).strip()
    return ""


def simulate_bank_response(
    req: SimulateResponseRequest,
) -> SimulateResponseResponse:
    """Emit a ``pacs.002`` status report for the inbound payload."""
    try:
        if req.desired_behavior == "RJCT" and not req.reason_code:
            raise InvalidInputError(
                "A reason_code is required to simulate an RJCT response.",
                locator="/reason_code",
            )
        try:
            root = fromstring(req.inbound_payload)
        except Exception as exc:  # noqa: BLE001 - normalize to typed error
            raise InvalidInputError(
                f"inbound_payload is not parseable XML: {exc}"
            ) from exc

        original_msg_id = _first_text(root, "MsgId") or "UNKNOWN"
        original_type = detect_message_type(req.inbound_payload) or "unknown"
        xml = _build_pacs002(
            original_msg_id,
            original_type,
            req.desired_behavior,
            req.reason_code,
        )
        return SimulateResponseResponse(
            status=req.desired_behavior,
            generated_response_type=_RESPONSE_TYPE,
            response_payload=xml,
        )
    except InvalidInputError as exc:
        return SimulateResponseResponse(error=exc.to_detail())
    except Exception as exc:  # noqa: BLE001 - boundary: return data, not trace
        return SimulateResponseResponse(
            error=ErrorDetail(
                code="RS_ERROR",
                explanation=f"Unexpected simulation error: {exc}",
            )
        )


def _build_pacs002(
    original_msg_id: str,
    original_type: str,
    status: str,
    reason_code: str | None,
) -> str:
    """Build a well-formed pacs.002 status report as escaped XML text."""
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    reason_block = ""
    if reason_code:
        reason_block = (
            "\n        <StsRsnInf><Rsn><Cd>"
            f"{escape(reason_code)}</Cd></Rsn></StsRsnInf>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:{_RESPONSE_TYPE}">\n'
        "  <FIToFIPmtStsRpt>\n"
        "    <GrpHdr>\n"
        f"      <MsgId>SIM-{escape(original_msg_id)}</MsgId>\n"
        f"      <CreDtTm>{created}</CreDtTm>\n"
        "    </GrpHdr>\n"
        "    <OrgnlGrpInfAndSts>\n"
        f"      <OrgnlMsgId>{escape(original_msg_id)}</OrgnlMsgId>\n"
        f"      <OrgnlMsgNmId>{escape(original_type)}</OrgnlMsgNmId>\n"
        f"      <GrpSts>{escape(status)}</GrpSts>{reason_block}\n"
        "    </OrgnlGrpInfAndSts>\n"
        "  </FIToFIPmtStsRpt>\n"
        "</Document>\n"
    )
