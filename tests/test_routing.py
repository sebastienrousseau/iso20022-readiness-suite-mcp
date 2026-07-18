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

"""Message-type detection and the validation route table."""

from __future__ import annotations

from iso20022_readiness_suite_mcp.orchestrators.routing import (
    detect_message_type,
    route_for,
)
from tests.conftest import CAMT_053, NON_ISO, PAIN_001


def test_detect_message_type_match() -> None:
    """A recognizable Document namespace yields the ISO message type."""
    assert detect_message_type(PAIN_001) == "pain.001.001.09"
    assert detect_message_type(CAMT_053) == "camt.053.001.08"


def test_detect_message_type_no_match() -> None:
    """A payload with no ISO namespace returns ``None``."""
    assert detect_message_type(NON_ISO) is None


def test_route_for_camt() -> None:
    """A camt.05x type routes to the camt053 statement validator."""
    route = route_for("camt.053.001.08")
    assert (route.server, route.tool) == (
        "camt053-mcp",
        "validate_statement",
    )
    assert route.build_args("<xml/>", "camt.053.001.08") == {"xml": "<xml/>"}


def test_route_for_pain() -> None:
    """A pain.00x type routes to the pain001 schema validator."""
    route = route_for("pain.001.001.09")
    assert (route.server, route.tool) == (
        "pain001-mcp",
        "validate_xml_against_schema",
    )
    assert route.build_args("<xml/>", "pain.001.001.09") == {
        "xml_content": "<xml/>",
        "message_type": "pain.001.001.09",
    }


def test_route_for_default() -> None:
    """An unknown/other type falls back to the generic gateway parser."""
    route = route_for("pacs.008.001.08")
    assert (route.server, route.tool) == ("iso20022-mcp", "parse")
    assert route.build_args("<xml/>", "pacs.008.001.08") == {
        "message_type": "pacs.008.001.08",
        "xml": "<xml/>",
    }
