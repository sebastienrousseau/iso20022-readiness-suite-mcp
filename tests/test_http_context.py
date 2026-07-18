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

"""Per-request tenant/scope context variables for the HTTP transport."""

from __future__ import annotations

from iso20022_readiness_suite_mcp.http import context


def test_tenant_header_constant() -> None:
    """The tenant header name is the documented ``X-MCP-Tenant``."""
    assert context.TENANT_HEADER == "X-MCP-Tenant"


def test_defaults_outside_a_request() -> None:
    """Outside any request the tenant is ``None`` and scopes are empty."""
    assert context.current_tenant() is None
    assert context.current_scopes() == ()


def test_tenant_set_and_reset() -> None:
    """Setting and resetting ``_tenant_var`` is reflected by the getter."""
    token = context._tenant_var.set("acme")
    try:
        assert context.current_tenant() == "acme"
    finally:
        context._tenant_var.reset(token)
    assert context.current_tenant() is None


def test_scopes_set_and_reset() -> None:
    """Setting and resetting ``_scopes_var`` is reflected by the getter."""
    token = context._scopes_var.set(("readiness:read",))
    try:
        assert context.current_scopes() == ("readiness:read",)
    finally:
        context._scopes_var.reset(token)
    assert context.current_scopes() == ()
