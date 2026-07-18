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

"""The package ``__version__`` matches the pyproject version of record."""

from __future__ import annotations

import re
from pathlib import Path

from iso20022_readiness_suite_mcp import __version__

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _pyproject_version() -> str:
    """Extract the poetry version from pyproject.toml via regex.

    Uses a regex rather than ``tomllib`` so the test runs identically on
    Python 3.10 (where ``tomllib`` is not in the standard library) and 3.11+.
    """
    text = _PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match is not None, "no version found in pyproject.toml"
    return match.group(1)


def test_version_matches_pyproject() -> None:
    """``__version__`` is exactly the poetry version in pyproject.toml."""
    assert __version__ == _pyproject_version()
