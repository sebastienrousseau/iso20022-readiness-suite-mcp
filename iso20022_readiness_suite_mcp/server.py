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

"""Model Context Protocol (MCP) server for the ISO 20022 readiness suite.

This is the orchestration front door: it is an MCP *server* to the outer
agent and an MCP *client* to the foundational servers (iso20022-mcp,
camt053-mcp, pain001-mcp, reconcile-mcp, bankstatementparser-mcp,
structured-address-fix-mcp). Every tool is a thin wrapper over an
orchestrator; each returns typed, JSON-serializable data and an
``{"error": ...}``-shaped payload on any failure, never a traceback.

Launch as a console script (``iso20022-readiness-suite-mcp``) or configure it
in an MCP client. The transport is stdio (FastMCP's default).
"""

from __future__ import annotations

import argparse
import json
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from iso20022_readiness_suite_mcp import __version__
from iso20022_readiness_suite_mcp.clients.sub_server import (
    StdioSubServerInvoker,
    SubServerInvoker,
)
from iso20022_readiness_suite_mcp.errors import UnknownProfileError
from iso20022_readiness_suite_mcp.models import (
    ClearingProfile,
    ReadinessCheckRequest,
    RemediateRequest,
    SimulateResponseRequest,
)
from iso20022_readiness_suite_mcp.orchestrators import readiness, simulator
from iso20022_readiness_suite_mcp.policies.engine import ProfileEngine

server = FastMCP("iso20022-readiness-suite")
# FastMCP does not accept a version kwarg; set it so serverInfo.version is
# coherent with the package version.
server._mcp_server.version = __version__

# Module singletons. Tests substitute ``_invoker`` with a fake so the
# orchestration logic is exercised without spawning real sub-processes.
_invoker: SubServerInvoker = StdioSubServerInvoker()
_engine: ProfileEngine = ProfileEngine.from_bundled()

# These tools reach external sub-servers, so they are read-only and
# non-destructive but open-world and not idempotent.
_ORCHESTRATE = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)
# The simulator is a purely local generator (closed-world).
_LOCAL = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)
_PURE_READ = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


@server.tool(title="List clearing profiles", annotations=_PURE_READ)
def list_profiles() -> list[dict[str, Any]]:
    """List the available clearing profiles (CBPR+, SEPA_Instant, ...).

    Use this to discover the ``target_profile`` values the other tools
    accept.
    """
    return [p.model_dump(mode="json") for p in _engine.list_profiles()]


@server.tool(title="Run ISO 20022 readiness check", annotations=_ORCHESTRATE)
async def run_readiness_check(
    payload_content: Annotated[
        str, Field(description="Raw ISO 20022 payload text (not a path).")
    ],
    filename_hint: Annotated[
        str | None, Field(default=None, description="Optional filename hint.")
    ] = None,
    target_profile: Annotated[
        str,
        Field(
            default="Generic",
            description="Clearing profile to lint against (see "
            "list_profiles).",
        ),
    ] = "Generic",
) -> dict[str, Any]:
    """Detect, validate, profile-lint, and score a payload's readiness.

    Args:
        payload_content: The raw ISO 20022 message text.
        filename_hint: Optional original filename, for routing.
        target_profile: The clearing profile to lint against.
    """
    request = ReadinessCheckRequest(
        payload_content=payload_content,
        filename_hint=filename_hint,
        target_profile=target_profile,
    )
    result = await readiness.run_readiness_check(request, _invoker, _engine)
    return result.model_dump(mode="json")


@server.tool(title="Remediate a payload", annotations=_ORCHESTRATE)
async def remediate_payload(
    payload_content: Annotated[
        str, Field(description="Raw ISO 20022 payload text to remediate.")
    ],
    target_profile: Annotated[
        str, Field(default="CBPR+", description="Profile driving remediation.")
    ] = "CBPR+",
) -> dict[str, Any]:
    """Apply automated remediation (e.g. Nov 2026 structured addresses).

    Args:
        payload_content: The raw ISO 20022 message text.
        target_profile: The clearing profile driving the remediation policy.
    """
    request = RemediateRequest(
        payload_content=payload_content, target_profile=target_profile
    )
    result = await readiness.remediate_payload(request, _invoker)
    return result.model_dump(mode="json")


@server.tool(title="Simulate a bank response", annotations=_LOCAL)
def simulate_bank_response(
    inbound_payload: Annotated[
        str, Field(description="The inbound initiation payload text.")
    ],
    desired_behavior: Annotated[
        str,
        Field(
            description="Desired outcome: 'ACCP', 'RJCT', or 'PDNG'.",
            json_schema_extra={"enum": ["ACCP", "RJCT", "PDNG"]},
        ),
    ],
    reason_code: Annotated[
        str | None,
        Field(
            default=None,
            description="ISO status reason code, e.g. 'AM04'. Required for "
            "RJCT.",
        ),
    ] = None,
) -> dict[str, Any]:
    """Emit a pacs.002 status report mocking a bank's response.

    Args:
        inbound_payload: The inbound initiation payload.
        desired_behavior: The status to simulate (ACCP / RJCT / PDNG).
        reason_code: The reason code (required when RJCT).
    """
    request = SimulateResponseRequest(
        inbound_payload=inbound_payload,
        desired_behavior=desired_behavior,
        reason_code=reason_code,
    )
    return simulator.simulate_bank_response(request).model_dump(mode="json")


@server.prompt(title="ISO 20022 readiness review")
def readiness_review(target_profile: str = "CBPR+") -> str:
    """Guide an agent through the end-to-end readiness workflow.

    Args:
        target_profile: The clearing profile the review should target
            (defaults to ``CBPR+``).
    """
    if target_profile == "Generic":
        profile_note = (
            "The 'Generic' baseline applies structural (XSD-level) checks "
            "only; expect no market-practice findings. Switch to a scheme "
            "profile (e.g. 'CBPR+', 'FedNow', 'SEPA_Instant') for "
            "clearing-specific rules."
        )
    else:
        profile_note = (
            f"The {target_profile!r} profile layers market-practice "
            "assertions on top of structural validation, so findings may "
            "include scheme-specific rules beyond raw XSD errors."
        )
    return (
        "You are reviewing an ISO 20022 payload for readiness against the "
        f"{target_profile!r} clearing profile. Work the tools in order:\n\n"
        "1. Call `list_profiles` to confirm "
        f"{target_profile!r} is registered and discover the exact "
        "`target_profile` value the other tools expect.\n"
        "2. Call `run_readiness_check` with the raw `payload_content` and "
        f"`target_profile={target_profile!r}` to detect the message type, "
        "validate it, profile-lint it, and get a readiness score plus "
        "structural errors and profile findings.\n"
        "3. If the check reports structural errors or profile findings, "
        "call `remediate_payload` with the same `payload_content` and "
        f"`target_profile={target_profile!r}` to apply automated fixes "
        "(e.g. the Nov 2026 structured-address requirements), then re-run "
        "step 2 on the mutated payload to confirm the findings cleared.\n"
        "4. Once the payload is clean, call `simulate_bank_response` with "
        "the initiation payload and a `desired_behavior` of 'ACCP', "
        "'RJCT', or 'PDNG' (supplying a `reason_code` such as 'AM04' when "
        "simulating 'RJCT') to preview the pacs.002 status report a bank "
        "would return.\n\n"
        f"{profile_note}"
    )


@server.resource("readiness://profiles", title="Clearing profile catalogue")
def readiness_profiles_resource() -> str:
    """Expose the full clearing-profile catalogue as a JSON resource.

    Reuses the :func:`list_profiles` tool so the resource and the tool never
    drift apart.
    """
    return json.dumps(list_profiles())


def _lookup_profile(profile_id: str) -> ClearingProfile:
    """Return the registered profile for ``profile_id``.

    Raises :class:`UnknownProfileError` when no such profile is registered.
    """
    for profile in _engine.list_profiles():
        if profile.profile_id == profile_id:
            return profile
    raise UnknownProfileError(
        f"No clearing profile registered for {profile_id!r}.",
        locator=f"readiness://profile/{profile_id}",
        context={
            "available": sorted(p.profile_id for p in _engine.list_profiles())
        },
    )


@server.resource(
    "readiness://profile/{profile_id}", title="Clearing profile summary"
)
def readiness_profile_resource(profile_id: str) -> str:
    """Summarise a single clearing profile addressed by ``profile_id``.

    Returns a JSON summary of the profile, or an ``{"error": ...}``-shaped
    :class:`~iso20022_readiness_suite_mcp.errors.ErrorDetail` payload (never a
    traceback) when the profile is not registered.
    """
    try:
        profile = _lookup_profile(profile_id)
    except UnknownProfileError as exc:
        return json.dumps({"error": exc.to_detail().model_dump(mode="json")})
    return json.dumps(
        {
            "profile_id": profile.profile_id,
            "market_practice": profile.market_practice,
            "supported_messages": list(profile.supported_messages),
            "rule_count": len(profile.custom_rules),
            "rule_ids": [rule.rule_id for rule in profile.custom_rules],
        }
    )


def main(argv: list[str] | None = None) -> None:
    """Run the MCP server over stdio (default) or streamable HTTP.

    ``--transport=http`` serves the authenticated streamable-HTTP transport
    (OAuth 2.1 resource server, or a static dev-mode bearer token); see
    :mod:`iso20022_readiness_suite_mcp.http.transport`.
    """
    parser = argparse.ArgumentParser(
        prog="iso20022-readiness-suite-mcp",
        description="ISO 20022 readiness/orchestration MCP server.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"iso20022-readiness-suite-mcp {__version__}",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default="stdio",
        help="Transport to serve (default: stdio).",
    )
    parser.add_argument(
        "--bind",
        default=None,
        metavar="HOST:PORT",
        help="Address for --transport=http (default: 127.0.0.1:8080).",
    )
    args = parser.parse_args(argv)
    if args.transport == "http":
        from iso20022_readiness_suite_mcp.http import transport

        transport.run_http(server, args.bind or transport.DEFAULT_BIND)
    else:
        server.run()


if __name__ == "__main__":  # pragma: no cover
    main()
