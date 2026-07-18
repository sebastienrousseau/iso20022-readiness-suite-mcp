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

"""Run every runnable Python snippet in the README and docs as part of CI.

Documentation code drifts silently because Markdown is never executed. This
test extracts each ```python fence from ``README.md`` and ``docs/*.md`` and
runs it in a subprocess (repo root on ``PYTHONPATH``, exactly as an installed
package would import). Illustrative fragments (no ``import``) and the HTTP
transport / CLI snippets (which need a running server) are skipped; every
self-contained snippet must exit 0, so any drift breaks the build.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_FENCE = re.compile(r"```(?:python|py)\n(.*?)```", re.DOTALL)


def _doc_files() -> list[Path]:
    """Return the README plus every docs page, when present."""
    files = [
        REPO_ROOT / "README.md",
        *sorted((REPO_ROOT / "docs").glob("*.md")),
    ]
    return [f for f in files if f.exists()]


def _runnable_snippets() -> list[tuple[str, str]]:
    """Return ``(id, code)`` for each self-contained runnable snippet."""
    snippets: list[tuple[str, str]] = []
    for doc in _doc_files():
        blocks = _FENCE.findall(doc.read_text(encoding="utf-8"))
        for index, code in enumerate(blocks, start=1):
            code = code.strip()
            # Skip illustrative fragments and server-transport / CLI examples.
            if "import" not in code:
                continue
            if "--transport" in code or "uvicorn" in code:
                continue
            snippets.append((f"{doc.name}#{index}", code))
    return snippets


_SNIPPETS = _runnable_snippets()


@pytest.mark.parametrize(
    "code",
    [code for _, code in _SNIPPETS],
    ids=[name for name, _ in _SNIPPETS],
)
def test_doc_snippet_runs(code: str) -> None:
    """Every runnable README/docs snippet exits cleanly (code 0)."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{REPO_ROOT}{os.pathsep}{existing}" if existing else str(REPO_ROOT)
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert result.returncode == 0, result.stderr
