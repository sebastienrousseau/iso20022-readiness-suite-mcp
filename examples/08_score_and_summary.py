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

"""Example: scoring findings and rendering an evidence summary.

The reports compiler turns raw structural and profile findings into a
0-100 readiness score, a letter grade, and a markdown summary suitable
for compliance sign-off. Fully local — no sub-server.

Usage::

    python examples/08_score_and_summary.py
"""

from iso20022_readiness_suite_mcp.errors import ErrorDetail
from iso20022_readiness_suite_mcp.reports import compiler


def main() -> None:
    """Score a sample finding set and print its grade and summary."""
    profile_findings = [
        ErrorDetail(
            code="CBPR_MISSING_COUNTRY",
            locator="Ctry",
            explanation="Postal address is missing a country element.",
            context={"severity": "error"},
        ),
    ]
    score = compiler.compute_score([], profile_findings)
    print(f"Score: {score}/100  (grade {compiler.grade(score)})")
    print()
    print(
        compiler.summary_markdown(
            "pain.001.001.09", score, [], profile_findings
        )
    )


if __name__ == "__main__":
    main()
