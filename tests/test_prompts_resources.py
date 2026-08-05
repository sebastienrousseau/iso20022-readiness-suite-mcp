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

"""The MCPServer prompt and resource surface (the MCP "Trinity")."""

from __future__ import annotations

import json

from iso20022_readiness_suite_mcp import server as server_mod


def test_readiness_review_prompt_registered() -> None:
    """The ``readiness_review`` prompt is registered with its argument."""
    prompts = {
        p.name: p for p in server_mod.server._prompt_manager.list_prompts()
    }
    assert "readiness_review" in prompts
    prompt = prompts["readiness_review"]
    assert prompt.title == "ISO 20022 readiness review"
    assert [a.name for a in (prompt.arguments or [])] == ["target_profile"]


def test_readiness_review_default_profile() -> None:
    """The default branch targets ``CBPR+`` and teaches the four-tool order."""
    guidance = server_mod.readiness_review()
    assert "'CBPR+'" in guidance
    # Pipeline is taught in order.
    order = [
        guidance.index("list_profiles"),
        guidance.index("run_readiness_check"),
        guidance.index("remediate_payload"),
        guidance.index("simulate_bank_response"),
    ]
    assert order == sorted(order)
    # The non-Generic branch is exercised by the default.
    assert "market-practice assertions" in guidance


def test_readiness_review_generic_branch() -> None:
    """The ``Generic`` branch flags the structural-only baseline."""
    guidance = server_mod.readiness_review(target_profile="Generic")
    assert "'Generic'" in guidance
    assert "structural (XSD-level) checks" in guidance


def test_profiles_resource_registered_and_matches_tool() -> None:
    """``readiness://profiles`` serialises the ``list_profiles`` tool output."""
    resources = {
        str(r.uri): r
        for r in server_mod.server._resource_manager.list_resources()
    }
    assert "readiness://profiles" in resources
    payload = json.loads(server_mod.readiness_profiles_resource())
    assert payload == server_mod.list_profiles()
    assert {p["profile_id"] for p in payload} == {
        "CBPR+",
        "FedNow",
        "SEPA_Instant",
        "Generic",
    }


def test_profile_resource_template_registered() -> None:
    """The per-profile resource is registered as a URI template."""
    templates = {
        t.uri_template: t
        for t in server_mod.server._resource_manager.list_templates()
    }
    assert "readiness://profile/{profile_id}" in templates


def test_profile_resource_known_profile() -> None:
    """A known ``profile_id`` yields a JSON summary of that profile."""
    summary = json.loads(server_mod.readiness_profile_resource("CBPR+"))
    assert summary["profile_id"] == "CBPR+"
    assert isinstance(summary["market_practice"], str)
    assert summary["rule_count"] == len(summary["rule_ids"])
    assert "error" not in summary


def test_profile_resource_unknown_profile() -> None:
    """An unknown ``profile_id`` returns a data-not-traceback error payload."""
    payload = json.loads(server_mod.readiness_profile_resource("Nope"))
    assert payload["error"]["code"] == "RS_UNKNOWN_PROFILE"
    assert payload["error"]["locator"] == "readiness://profile/Nope"
    assert "CBPR+" in payload["error"]["context"]["available"]
