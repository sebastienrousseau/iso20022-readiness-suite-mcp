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

"""Example: automated remediation with a stub sub-server.

Remediation is delegated to ``structured-address-fix-mcp``. This example
injects a **stub invoker** returning a canned patched payload instead of
spawning that server, so it runs fully offline. In production the server
reaches the live remediation server over stdio.

Usage::

    python examples/04_remediate_payload.py
"""

import asyncio
from collections.abc import Mapping
from typing import Any

from iso20022_readiness_suite_mcp.clients.sub_server import ToolOutcome
from iso20022_readiness_suite_mcp.models import RemediateRequest
from iso20022_readiness_suite_mcp.orchestrators import readiness

_ORIGINAL = (
    '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.09">'
    "<Cdtr><PstlAdr><StrtNm>Main St</StrtNm></PstlAdr></Cdtr></Document>"
)
_PATCHED = _ORIGINAL.replace(
    "<StrtNm>Main St</StrtNm>",
    "<StrtNm>Main St</StrtNm><TwnNm>London</TwnNm><Ctry>GB</Ctry>",
)


class StubInvoker:
    """A stand-in for structured-address-fix-mcp returning a fixed patch."""

    async def call(
        self, server: str, tool: str, arguments: Mapping[str, Any]
    ) -> ToolOutcome:
        """Return a canned remediation result without any sub-process."""
        return ToolOutcome(
            ok=True,
            data={
                "patched_xml": _PATCHED,
                "suggestions": [
                    {
                        "explanation": "Added structured TwnNm and Ctry.",
                        "residual_findings": [],
                    }
                ],
            },
        )


def main() -> None:
    """Remediate a payload and print the fixes log and applied flag."""
    request = RemediateRequest(
        payload_content=_ORIGINAL, target_profile="CBPR+"
    )
    response = asyncio.run(readiness.remediate_payload(request, StubInvoker()))
    print(f"Remediation applied: {response.remediation_applied}")
    print("Fixes:")
    for fix in response.fixes_log:
        print(f"  - {fix}")
    print(f"Mutated payload changed: {response.mutated_payload != _ORIGINAL}")


if __name__ == "__main__":
    main()
