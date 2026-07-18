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

"""Example: ``simulate_bank_response`` — an accepted (ACCP) status.

The simulator is a purely local generator (no sub-server): it emits a
well-formed ``pacs.002`` status report cross-referencing the inbound
initiation message. Useful as an offline mock for integration testing.

Usage::

    python examples/05_simulate_accept.py
"""

from iso20022_readiness_suite_mcp.server import simulate_bank_response

_INBOUND = (
    '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.09">'
    "<CstmrCdtTrfInitn><GrpHdr><MsgId>PMT-42</MsgId></GrpHdr>"
    "</CstmrCdtTrfInitn></Document>"
)


def main() -> None:
    """Simulate an accepted payment and print the pacs.002 report."""
    result = simulate_bank_response(_INBOUND, "ACCP")
    print(f"Status               : {result['status']}")
    print(f"Generated response   : {result['generated_response_type']}")
    print("Response payload:")
    print(result["response_payload"])


if __name__ == "__main__":
    main()
