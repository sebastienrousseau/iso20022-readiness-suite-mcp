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

"""Message-type detection and validation routing.

Detection is deterministic and local (the ISO 20022 message type is read from
the ``<Document xmlns=...>`` namespace), so it never needs a sub-server. The
route table maps a message-type family to the underlying server, tool, and
argument shape that structurally validates a raw payload of that family — the
argument names are taken verbatim from each server's real tool schema.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any, NamedTuple

_NS_RE = re.compile(
    r"urn:iso:std:iso:20022:tech:xsd:([a-z]+\.[0-9]{3}\.[0-9]{3}\.[0-9]{2})"
)


def detect_message_type(payload: str) -> str | None:
    """Return the ISO 20022 message type from the Document namespace.

    E.g. ``pain.001.001.09``. Returns ``None`` when the payload carries no
    recognizable ISO 20022 namespace.
    """
    match = _NS_RE.search(payload)
    return match.group(1) if match else None


class ValidationRoute(NamedTuple):
    """Where and how to structurally validate a payload family."""

    server: str
    tool: str
    build_args: Callable[[str, str], Mapping[str, Any]]


#: Message-type prefix -> validation route. The default route parses via the
#: generic gateway to confirm structural parseability.
_ROUTES: tuple[tuple[str, ValidationRoute], ...] = (
    (
        "camt.05",
        ValidationRoute(
            "camt053-mcp",
            "validate_statement",
            lambda payload, _mt: {"xml": payload},
        ),
    ),
    (
        "pain.00",
        ValidationRoute(
            "pain001-mcp",
            "validate_xml_against_schema",
            lambda payload, mt: {"xml_content": payload, "message_type": mt},
        ),
    ),
)

_DEFAULT_ROUTE = ValidationRoute(
    "iso20022-mcp",
    "parse",
    lambda payload, mt: {"message_type": mt, "xml": payload},
)


def route_for(message_type: str) -> ValidationRoute:
    """Return the validation route for ``message_type``."""
    for prefix, route in _ROUTES:
        if message_type.startswith(prefix):
            return route
    return _DEFAULT_ROUTE
