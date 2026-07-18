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

"""The FastMCP tool surface and the ``main`` console entry point."""

from __future__ import annotations

import pytest

from iso20022_readiness_suite_mcp import __version__
from iso20022_readiness_suite_mcp import server as server_mod
from iso20022_readiness_suite_mcp.clients.sub_server import ToolOutcome
from tests.conftest import PAIN_001, FakeInvoker


def test_list_profiles_tool() -> None:
    """``list_profiles`` returns JSON-ready dicts for every profile."""
    profiles = server_mod.list_profiles()
    ids = {p["profile_id"] for p in profiles}
    assert ids == {"CBPR+", "FedNow", "SEPA_Instant", "Generic"}


@pytest.mark.asyncio
async def test_run_readiness_check_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The readiness tool wires the request through the orchestrator."""
    monkeypatch.setattr(
        server_mod,
        "_invoker",
        FakeInvoker(ToolOutcome(ok=True, data={"valid": True})),
    )
    result = await server_mod.run_readiness_check(
        PAIN_001, target_profile="CBPR+"
    )
    assert result["message_type"] == "pain.001.001.09"
    assert result["is_valid"] is True
    assert result["readiness_score"] == 70


@pytest.mark.asyncio
async def test_remediate_payload_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The remediate tool returns a JSON-ready remediation outcome."""
    data = {
        "patched_xml": "<Document>patched</Document>",
        "suggestions": [{"explanation": "Added Ctry"}],
    }
    monkeypatch.setattr(
        server_mod, "_invoker", FakeInvoker(ToolOutcome(ok=True, data=data))
    )
    result = await server_mod.remediate_payload("<Document>orig</Document>")
    assert result["remediation_applied"] is True
    assert result["fixes_log"] == ["Added Ctry"]


def test_simulate_bank_response_tool() -> None:
    """The simulate tool returns a JSON-ready pacs.002 response."""
    result = server_mod.simulate_bank_response(PAIN_001, "ACCP")
    assert result["status"] == "ACCP"
    assert result["generated_response_type"] == "pacs.002.001.10"
    assert "<GrpSts>ACCP</GrpSts>" in result["response_payload"]


def test_main_version_exits(capsys: pytest.CaptureFixture[str]) -> None:
    """``main(['--version'])`` prints the version and exits."""
    with pytest.raises(SystemExit) as info:
        server_mod.main(["--version"])
    assert info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_main_runs_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """``main([])`` parses args and hands off to the FastMCP run loop."""
    called: list[bool] = []
    monkeypatch.setattr(server_mod.server, "run", lambda: called.append(True))
    server_mod.main([])
    assert called == [True]
