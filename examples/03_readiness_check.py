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

"""Example: end-to-end readiness check with a stub sub-server.

The readiness orchestrator depends only on the ``SubServerInvoker``
protocol, so this example injects a **stub invoker** that reports the
payload structurally valid instead of spawning the real ``pain001-mcp``.
The clearing-profile linting and scoring are real. In production the
server uses the stdio invoker to reach the live foundational servers.

Usage::

    python examples/03_readiness_check.py
"""

import asyncio
from collections.abc import Mapping
from typing import Any

from iso20022_readiness_suite_mcp.clients.sub_server import ToolOutcome
from iso20022_readiness_suite_mcp.models import ReadinessCheckRequest
from iso20022_readiness_suite_mcp.orchestrators import readiness
from iso20022_readiness_suite_mcp.policies.engine import ProfileEngine

# A pain.001 whose creditor address has neither Ctry nor TwnNm, so the
# CBPR+ profile raises two findings.
_PAYLOAD = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.09">
  <CstmrCdtTrfInitn>
    <GrpHdr><MsgId>DEMO-1</MsgId></GrpHdr>
    <PmtInf><Cdtr><Nm>Acme Ltd</Nm>
      <PstlAdr><StrtNm>Main St</StrtNm></PstlAdr>
    </Cdtr></PmtInf>
  </CstmrCdtTrfInitn>
</Document>
"""


class StubInvoker:
    """A stand-in for the real stdio invoker: always reports 'valid'."""

    async def call(
        self, server: str, tool: str, arguments: Mapping[str, Any]
    ) -> ToolOutcome:
        """Return a structurally-valid outcome without any sub-process."""
        return ToolOutcome(ok=True, data={"valid": True})


def main() -> None:
    """Run a CBPR+ readiness check and print the score and findings."""
    request = ReadinessCheckRequest(
        payload_content=_PAYLOAD, target_profile="CBPR+"
    )
    response = asyncio.run(
        readiness.run_readiness_check(
            request, StubInvoker(), ProfileEngine.from_bundled()
        )
    )
    print(f"Message type   : {response.message_type}")
    print(f"Structurally OK: {response.is_valid}")
    print(f"Readiness score: {response.readiness_score}/100")
    print("Profile findings:")
    for finding in response.profile_findings:
        print(f"  - {finding.code}: {finding.explanation}")


if __name__ == "__main__":
    main()
