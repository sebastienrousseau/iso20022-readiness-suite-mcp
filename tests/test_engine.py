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

"""The clearing-profile policy engine: loading, registration, evaluation."""

from __future__ import annotations

import pytest

from iso20022_readiness_suite_mcp.errors import (
    InvalidInputError,
    UnknownProfileError,
)
from iso20022_readiness_suite_mcp.models import ClearingProfile, ProfileRule
from iso20022_readiness_suite_mcp.policies import engine as engine_mod
from iso20022_readiness_suite_mcp.policies.engine import ProfileEngine
from tests.conftest import (
    PAIN_001,
    PAIN_001_COMPLIANT,
    SEPA_EUR_BAD,
    SEPA_EUR_GOOD,
    SEPA_USD,
)


@pytest.fixture
def engine() -> ProfileEngine:
    """The bundled clearing-profile engine."""
    return ProfileEngine.from_bundled()


def test_from_bundled_loads_four_profiles(engine: ProfileEngine) -> None:
    """The four baseline profiles ship bundled with the package."""
    ids = {p.profile_id for p in engine.list_profiles()}
    assert ids == {"CBPR+", "FedNow", "SEPA_Instant", "Generic"}


class _FakeEntry:
    """A directory entry exposing ``.name`` and ``.read_text``."""

    def __init__(self, name: str, text: str = "") -> None:
        """Store the entry name and its text payload."""
        self.name = name
        self._text = text

    def read_text(self, encoding: str = "utf-8") -> str:
        """Return the stored text payload."""
        return self._text


class _FakeDir:
    """A traversable directory yielding fixed entries from ``iterdir``."""

    def __init__(self, entries: list[_FakeEntry]) -> None:
        """Store the entries this directory yields."""
        self._entries = entries

    def iterdir(self) -> list[_FakeEntry]:
        """Return the fixed directory entries."""
        return list(self._entries)


class _FakeRoot:
    """A traversable whose ``joinpath`` always returns the fake profiles dir."""

    def __init__(self, directory: _FakeDir) -> None:
        """Store the directory ``joinpath`` returns."""
        self._dir = directory

    def joinpath(self, name: str) -> _FakeDir:
        """Return the stored fake directory, ignoring ``name``."""
        return self._dir


def test_from_bundled_skips_non_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-``.json`` directory entries are skipped during loading."""
    profile_json = (
        '{"profile_id": "OnlyOne", "market_practice": "m", '
        '"supported_messages": [], "custom_rules": []}'
    )
    directory = _FakeDir(
        [
            _FakeEntry("README.txt", "ignore me"),
            _FakeEntry("only_one.json", profile_json),
        ]
    )
    monkeypatch.setattr(
        engine_mod.resources, "files", lambda pkg: _FakeRoot(directory)
    )
    loaded = ProfileEngine.from_bundled()
    assert [p.profile_id for p in loaded.list_profiles()] == ["OnlyOne"]


def test_apply_unknown_profile_raises(engine: ProfileEngine) -> None:
    """An unregistered profile id raises ``UnknownProfileError``."""
    with pytest.raises(UnknownProfileError) as info:
        engine.apply("NoSuch", PAIN_001)
    assert "available" in info.value.context


def test_apply_unparseable_xml_raises(engine: ProfileEngine) -> None:
    """Unparseable XML raises ``InvalidInputError``."""
    with pytest.raises(InvalidInputError):
        engine.apply("CBPR+", "definitely not xml <<<")


def test_required_rule_violated(engine: ProfileEngine) -> None:
    """A missing required element produces a finding per rule."""
    findings = engine.apply("CBPR+", PAIN_001)
    assert {f.code for f in findings} == {
        "CBPR_MISSING_COUNTRY",
        "CBPR_MISSING_TOWN",
    }
    assert findings[0].context == {
        "rule_id": "cbpr-ctry",
        "severity": "error",
    }


def test_required_rule_satisfied(engine: ProfileEngine) -> None:
    """A fully structured address satisfies the required rules."""
    assert engine.apply("CBPR+", PAIN_001_COMPLIANT) == []


def test_conditional_rule_not_applicable(engine: ProfileEngine) -> None:
    """The SEPA conditional does not fire when the condition is unmet."""
    assert engine.apply("SEPA_Instant", SEPA_USD) == []


def test_conditional_rule_violated(engine: ProfileEngine) -> None:
    """An EUR payment whose ChrgBr is not SLEV violates the SEPA rule."""
    findings = engine.apply("SEPA_Instant", SEPA_EUR_BAD)
    assert [f.code for f in findings] == ["SEPA_CHRGBR_NOT_SLEV"]


def test_conditional_rule_satisfied(engine: ProfileEngine) -> None:
    """An EUR payment with ChrgBr SLEV satisfies the SEPA rule."""
    assert engine.apply("SEPA_Instant", SEPA_EUR_GOOD) == []


def _equals_profile() -> ClearingProfile:
    """A one-rule profile asserting the Ccy element equals EUR."""
    return ClearingProfile(
        profile_id="EqCheck",
        market_practice="test",
        custom_rules=(
            ProfileRule(
                rule_id="eq-ccy",
                description="Ccy must be EUR.",
                locator="Ccy",
                assertion="equals:EUR",
                error_code="CCY_NOT_EUR",
            ),
        ),
    )


def test_register_and_equals_satisfied(engine: ProfileEngine) -> None:
    """A registered equals-rule passes when the text matches."""
    engine.register(_equals_profile())
    assert engine.apply("EqCheck", SEPA_EUR_BAD) == []


def test_equals_violated(engine: ProfileEngine) -> None:
    """An equals-rule fails when the element text differs."""
    engine.register(_equals_profile())
    findings = engine.apply("EqCheck", SEPA_USD)
    assert [f.code for f in findings] == ["CCY_NOT_EUR"]


def test_register_replaces_existing() -> None:
    """Registering the same id replaces the prior profile."""
    engine = ProfileEngine({})
    engine.register(_equals_profile())
    replacement = ClearingProfile(profile_id="EqCheck", market_practice="v2")
    engine.register(replacement)
    assert engine.apply("EqCheck", SEPA_USD) == []  # no rules now
    assert len(engine.list_profiles()) == 1
