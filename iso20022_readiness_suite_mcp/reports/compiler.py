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

"""Readiness scoring and evidence-summary assembly.

Turns raw structural and profile findings into a 0-100 readiness score, a
letter grade, and a human-readable markdown summary suitable for compliance
sign-off.
"""

from __future__ import annotations

from collections.abc import Sequence

from iso20022_readiness_suite_mcp.errors import ErrorDetail

#: Score penalty per structural (schema) error — these block acceptance.
_STRUCTURAL_PENALTY = 25
#: Score penalty per profile finding, by severity.
_PROFILE_PENALTY = {"error": 15, "warning": 5, "info": 0}


def compute_score(
    structural_errors: Sequence[ErrorDetail],
    profile_findings: Sequence[ErrorDetail],
) -> int:
    """Return a 0-100 readiness score from the finding sets.

    A payload with no findings scores 100; structural errors are penalised
    most heavily, profile findings by their severity. The score floors at 0.
    """
    penalty = _STRUCTURAL_PENALTY * len(structural_errors)
    for finding in profile_findings:
        severity = str(finding.context.get("severity", "error"))
        penalty += _PROFILE_PENALTY.get(severity, _PROFILE_PENALTY["error"])
    return max(0, 100 - penalty)


def grade(score: int) -> str:
    """Map a readiness score to a letter grade (A/B/C/F)."""
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 50:
        return "C"
    return "F"


def summary_markdown(
    message_type: str,
    score: int,
    structural_errors: Sequence[ErrorDetail],
    profile_findings: Sequence[ErrorDetail],
) -> str:
    """Assemble a markdown readiness summary for an evidence pack."""
    lines = [
        "# ISO 20022 readiness summary",
        "",
        f"- **Message type**: {message_type or 'unknown'}",
        f"- **Readiness score**: {score}/100 (grade {grade(score)})",
        f"- **Structural errors**: {len(structural_errors)}",
        f"- **Profile findings**: {len(profile_findings)}",
        "",
    ]
    if structural_errors:
        lines.append("## Structural errors")
        lines += [
            f"- `{e.code}` at `{e.locator}` — {e.explanation}"
            for e in structural_errors
        ]
        lines.append("")
    if profile_findings:
        lines.append("## Profile findings")
        lines += [
            f"- `{e.code}` at `{e.locator}` — {e.explanation}"
            for e in profile_findings
        ]
        lines.append("")
    if not structural_errors and not profile_findings:
        lines.append("No findings — the payload meets the selected profile.")
    return "\n".join(lines)
