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

"""Exercise every shipping example end-to-end as part of CI.

Each ``examples/*.py`` script is run in a subprocess with the current
interpreter; the test passes when the process exits 0. This keeps the
examples aligned with the public server shape -- any drift breaks the
build.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"


def _example_paths() -> list[Path]:
    """Return every runnable example script, sorted by name."""
    return sorted(EXAMPLES_DIR.glob("*.py"))


@pytest.mark.parametrize(
    "example",
    _example_paths(),
    ids=lambda p: p.stem,
)
def test_example_runs(example: Path) -> None:
    """Running the example as a subprocess exits cleanly (code 0)."""
    # A script run as ``python examples/<x>.py`` puts ``examples/`` on
    # sys.path[0], not the repo root, so make the package importable via
    # PYTHONPATH -- exactly as a ``pip install`` would for an end user.
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{REPO_ROOT}{os.pathsep}{existing}" if existing else str(REPO_ROOT)
    )
    result = subprocess.run(
        [sys.executable, str(example)],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert result.returncode == 0, result.stderr
