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

"""The clearing-profile policy engine.

Profiles capture market-practice assertions that lie *beyond* structural XSD
validation (e.g. "if currency is EUR, ChrgBr must be SLEV"). They are pure
data — bundled JSON for the open baseline profiles, and loadable at runtime
for premium bank-specific rule packs. XML is parsed with ``defusedxml`` only.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from defusedxml.ElementTree import fromstring

from iso20022_readiness_suite_mcp.errors import (
    ErrorDetail,
    InvalidInputError,
    UnknownProfileError,
)
from iso20022_readiness_suite_mcp.models import ClearingProfile, ProfileRule


def _local(tag: str) -> str:
    """Return an element's local name, stripping any ``{namespace}``."""
    return tag.rsplit("}", 1)[-1]


def _find_text(root: Any, element: str) -> str | None:
    """Return the text of the first descendant with local name ``element``."""
    for node in root.iter():
        if _local(node.tag) == element and node.text is not None:
            return str(node.text).strip()
    return None


class ProfileEngine:
    """Loads clearing profiles and evaluates them against a payload."""

    def __init__(self, profiles: dict[str, ClearingProfile]) -> None:
        """Store the registered profiles keyed by ``profile_id``."""
        self._profiles = dict(profiles)

    @classmethod
    def from_bundled(cls) -> ProfileEngine:
        """Load the baseline (open-source) profiles bundled with the package."""
        profiles: dict[str, ClearingProfile] = {}
        root = resources.files("iso20022_readiness_suite_mcp.data").joinpath(
            "profiles"
        )
        for entry in root.iterdir():
            if entry.name.endswith(".json"):
                data = json.loads(entry.read_text(encoding="utf-8"))
                profile = ClearingProfile.model_validate(data)
                profiles[profile.profile_id] = profile
        return cls(profiles)

    def list_profiles(self) -> list[ClearingProfile]:
        """Return every registered profile."""
        return list(self._profiles.values())

    def register(self, profile: ClearingProfile) -> None:
        """Register (or replace) a profile, e.g. a premium rule pack."""
        self._profiles[profile.profile_id] = profile

    def apply(self, profile_id: str, xml_content: str) -> list[ErrorDetail]:
        """Evaluate ``profile_id`` against ``xml_content``.

        Returns an ordered list of findings (empty when compliant). Raises
        :class:`UnknownProfileError` for an unregistered id and
        :class:`InvalidInputError` for unparseable XML.
        """
        profile = self._profiles.get(profile_id)
        if profile is None:
            raise UnknownProfileError(
                f"No clearing profile registered for {profile_id!r}.",
                context={"available": sorted(self._profiles)},
            )
        try:
            root = fromstring(xml_content)
        except Exception as exc:  # noqa: BLE001 - normalize to a typed error
            raise InvalidInputError(
                f"Payload is not parseable XML: {exc}"
            ) from exc
        return [
            finding
            for rule in profile.custom_rules
            if (finding := self._evaluate(rule, root)) is not None
        ]

    def _evaluate(self, rule: ProfileRule, root: Any) -> ErrorDetail | None:
        """Evaluate one rule; return a finding when it is violated.

        The assertion mini-language supports three forms:
        ``required`` (the ``locator`` element must be present),
        ``equals:<value>`` (its text must equal ``<value>``), and
        ``if:<elem>=<val>:equals:<val2>`` (conditional).
        """
        assertion = rule.assertion
        if assertion == "required":
            violated = _find_text(root, rule.locator) is None
        elif assertion.startswith("equals:"):
            expected = assertion.split(":", 1)[1]
            violated = _find_text(root, rule.locator) != expected
        elif assertion.startswith("if:"):
            violated = self._eval_conditional(assertion, rule.locator, root)
        else:  # pragma: no cover - guarded by profile validation upstream
            violated = False
        if not violated:
            return None
        return ErrorDetail(
            code=rule.error_code,
            locator=rule.locator,
            explanation=rule.description,
            context={"rule_id": rule.rule_id, "severity": rule.severity},
        )

    def _eval_conditional(
        self, assertion: str, locator: str, root: Any
    ) -> bool:
        """Evaluate an ``if:<elem>=<val>:equals:<val2>`` assertion."""
        _, condition, _, expected = assertion.split(":", 3)
        cond_elem, cond_val = condition.split("=", 1)
        if _find_text(root, cond_elem) != cond_val:
            return False  # condition not met -> rule does not apply
        return _find_text(root, locator) != expected
