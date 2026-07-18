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

"""Example: linting a payload against a clearing profile directly.

The :class:`ProfileEngine` evaluates market-practice assertions that lie
beyond XSD validation. This runs entirely locally against the bundled
profiles — no sub-server involved.

Usage::

    python examples/07_apply_profile.py
"""

from iso20022_readiness_suite_mcp.policies.engine import ProfileEngine

_PAYLOAD = (
    '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.09">'
    "<Cdtr><PstlAdr><StrtNm>Main St</StrtNm></PstlAdr></Cdtr></Document>"
)


def main() -> None:
    """Apply the CBPR+ profile and print each finding it raises."""
    engine = ProfileEngine.from_bundled()
    findings = engine.apply("CBPR+", _PAYLOAD)
    print(f"CBPR+ raised {len(findings)} finding(s):")
    for finding in findings:
        severity = finding.context.get("severity", "error")
        print(
            f"  [{severity}] {finding.code} at {finding.locator}: "
            f"{finding.explanation}"
        )


if __name__ == "__main__":
    main()
