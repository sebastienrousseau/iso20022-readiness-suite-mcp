#!/usr/bin/env python3
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

"""Example: ``simulate_bank_response`` — a rejection (RJCT) with a reason.

An RJCT requires an ISO external status reason code (e.g. ``AM04``,
insufficient funds); it is embedded in the generated ``pacs.002`` as a
``<StsRsnInf>`` block. Omitting the reason code returns a typed
``RS_INVALID_INPUT`` error instead — also shown here.

Usage::

    python examples/06_simulate_reject.py
"""

from iso20022_readiness_suite_mcp.server import simulate_bank_response

_INBOUND = (
    '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.09">'
    "<CstmrCdtTrfInitn><GrpHdr><MsgId>PMT-99</MsgId></GrpHdr>"
    "</CstmrCdtTrfInitn></Document>"
)


def main() -> None:
    """Simulate a rejection with a reason, then one missing its reason."""
    ok = simulate_bank_response(_INBOUND, "RJCT", reason_code="AM04")
    print("With reason code AM04:")
    print(f"  status: {ok['status']}")
    has_reason = "<Cd>AM04</Cd>" in ok["response_payload"]
    print(f"  reason block present: {has_reason}")

    missing = simulate_bank_response(_INBOUND, "RJCT")
    print("Without a reason code (invalid):")
    print(f"  error code: {missing['error']['code']}")
    print(f"  explanation: {missing['error']['explanation']}")


if __name__ == "__main__":
    main()
