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

"""Per-request context for the HTTP transport: tenant scope and token scopes.

The auth middleware forwards two pieces of request context into
:class:`contextvars.ContextVar` slots for the duration of a single HTTP
request: the optional tenant identifier (from the ``X-MCP-Tenant`` header)
and the authenticated token's OAuth scopes. Tools read them through
:func:`current_tenant` and :func:`current_scopes`; under the stdio transport
both are simply empty, so tool code never needs to branch on the transport.
"""

from __future__ import annotations

from contextvars import ContextVar

#: The HTTP header naming the tenant/account scope of a call (optional).
TENANT_HEADER = "X-MCP-Tenant"

#: The tenant identifier for the current request, or ``None``.
_tenant_var: ContextVar[str | None] = ContextVar("_tenant_var", default=None)

#: The authenticated token's OAuth scopes for the current request.
_scopes_var: ContextVar[tuple[str, ...]] = ContextVar(
    "_scopes_var", default=()
)


def current_tenant() -> str | None:
    """Return the tenant scope of the current request, if any."""
    return _tenant_var.get()


def current_scopes() -> tuple[str, ...]:
    """Return the authenticated token's scopes for the current request."""
    return _scopes_var.get()
