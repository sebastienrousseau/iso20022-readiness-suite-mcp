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

"""Readiness scoring, grade banding, and markdown summary assembly."""

from __future__ import annotations

import pytest

from iso20022_readiness_suite_mcp.errors import ErrorDetail
from iso20022_readiness_suite_mcp.reports import compiler


def _finding(severity: str | None = None) -> ErrorDetail:
    """A profile finding, optionally carrying a severity in its context."""
    context = {"severity": severity} if severity is not None else {}
    return ErrorDetail(code="F", explanation="finding", context=context)


def test_score_perfect() -> None:
    """No findings scores a perfect 100."""
    assert compiler.compute_score([], []) == 100


def test_score_structural_penalty() -> None:
    """Each structural error costs 25 points."""
    assert compiler.compute_score([_finding(), _finding()], []) == 50


def test_score_profile_severity_weights() -> None:
    """Profile penalties follow the per-severity weights."""
    findings = [_finding("error"), _finding("warning"), _finding("info")]
    # 100 - 15 - 5 - 0 = 80
    assert compiler.compute_score([], findings) == 80


def test_score_default_severity_is_error() -> None:
    """A finding with no severity context is penalised as an error."""
    assert compiler.compute_score([], [_finding()]) == 85


def test_score_unknown_severity_defaults_error() -> None:
    """An unrecognised severity string is penalised as an error."""
    assert compiler.compute_score([], [_finding("critical")]) == 85


def test_score_floors_at_zero() -> None:
    """A heavily-penalised payload floors at zero, never negative."""
    structural = [_finding() for _ in range(10)]
    assert compiler.compute_score(structural, []) == 0


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (100, "A"),
        (90, "A"),
        (89, "B"),
        (75, "B"),
        (74, "C"),
        (50, "C"),
        (49, "F"),
        (0, "F"),
    ],
)
def test_grade_bands(score: int, expected: str) -> None:
    """Scores map to the A/B/C/F letter bands at their boundaries."""
    assert compiler.grade(score) == expected


def test_summary_no_findings() -> None:
    """A clean payload renders the 'no findings' summary branch."""
    md = compiler.summary_markdown("pain.001.001.09", 100, [], [])
    assert "No findings" in md
    assert "## Structural errors" not in md
    assert "## Profile findings" not in md
    assert "grade A" in md


def test_summary_with_findings() -> None:
    """Structural and profile findings each render their own section."""
    structural = [ErrorDetail(code="S1", locator="/a", explanation="bad")]
    profile = [ErrorDetail(code="P1", locator="/b", explanation="lint")]
    md = compiler.summary_markdown("pain.001.001.09", 60, structural, profile)
    assert "## Structural errors" in md
    assert "`S1` at `/a` — bad" in md
    assert "## Profile findings" in md
    assert "`P1` at `/b` — lint" in md
    assert "No findings" not in md


def test_summary_unknown_message_type() -> None:
    """An empty message type renders as 'unknown' in the summary."""
    md = compiler.summary_markdown("", 100, [], [])
    assert "**Message type**: unknown" in md
