#!/usr/bin/env python3
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

"""Example: message-type detection and validation routing.

Detection is deterministic and local (read from the ``<Document xmlns=...>``
namespace), so no sub-server is required. ``route_for`` then shows which
foundational server would structurally validate each family.

Usage::

    python examples/02_detect_and_route.py
"""

from iso20022_readiness_suite_mcp.orchestrators.routing import (
    detect_message_type,
    route_for,
)

_SAMPLES = {
    "pain.001": '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:'
    'pain.001.001.09"/>',
    "camt.053": '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:'
    'camt.053.001.08"/>',
    "pacs.008": '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:'
    'pacs.008.001.08"/>',
    "not-iso": "<x/>",
}


def main() -> None:
    """Detect the message type of each sample and print its route."""
    for label, payload in _SAMPLES.items():
        message_type = detect_message_type(payload)
        if message_type is None:
            print(f"  {label:<9} -> no ISO 20022 namespace detected")
            continue
        route = route_for(message_type)
        print(
            f"  {label:<9} -> {message_type} validated by "
            f"{route.server}/{route.tool}"
        )


if __name__ == "__main__":
    main()
