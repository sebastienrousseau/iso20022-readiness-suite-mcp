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

"""Shared fixtures for the iso20022-readiness-suite-mcp test suite.

Provides sample ISO 20022 payloads and a configurable fake
:class:`SubServerInvoker` so the orchestration logic is exercised without
ever spawning a real sub-process.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from iso20022_readiness_suite_mcp.clients.sub_server import ToolOutcome

#: A pain.001 with a Cdtr/PstlAdr but no Ctry/TwnNm -> two CBPR+ findings.
PAIN_001 = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.09">
  <CstmrCdtTrfInitn>
    <GrpHdr><MsgId>MSG-1</MsgId></GrpHdr>
    <PmtInf>
      <Cdtr>
        <Nm>Acme Ltd</Nm>
        <PstlAdr><StrtNm>Main St</StrtNm></PstlAdr>
      </Cdtr>
    </PmtInf>
  </CstmrCdtTrfInitn>
</Document>
"""

#: A pain.001 whose Cdtr address is fully structured (no CBPR+ findings).
PAIN_001_COMPLIANT = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.09">
  <CstmrCdtTrfInitn>
    <GrpHdr><MsgId>MSG-2</MsgId></GrpHdr>
    <PmtInf>
      <Cdtr>
        <Nm>Acme Ltd</Nm>
        <PstlAdr>
          <StrtNm>Main St</StrtNm>
          <TwnNm>London</TwnNm>
          <Ctry>GB</Ctry>
        </PstlAdr>
      </Cdtr>
    </PmtInf>
  </CstmrCdtTrfInitn>
</Document>
"""

#: A camt.053 statement (routes to camt053-mcp/validate_statement).
CAMT_053 = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08">
  <BkToCstmrStmt>
    <GrpHdr><MsgId>STMT-1</MsgId></GrpHdr>
  </BkToCstmrStmt>
</Document>
"""

#: A SEPA-style payment in EUR whose ChrgBr is not SLEV (violates SEPA rule).
SEPA_EUR_BAD = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.09">
  <CstmrCdtTrfInitn>
    <PmtInf>
      <Ccy>EUR</Ccy>
      <ChrgBr>DEBT</ChrgBr>
    </PmtInf>
  </CstmrCdtTrfInitn>
</Document>
"""

#: The same SEPA payment with a compliant SLEV charge bearer.
SEPA_EUR_GOOD = SEPA_EUR_BAD.replace("DEBT", "SLEV")

#: A EUR-free payment: the SEPA conditional rule does not apply at all.
SEPA_USD = SEPA_EUR_BAD.replace("EUR", "USD")

#: A payload with no ISO 20022 namespace at all.
NON_ISO = "<x/>"


class FakeInvoker:
    """A :class:`SubServerInvoker` that records calls and returns a fixed
    :class:`ToolOutcome`, so orchestrators run without any sub-process."""

    def __init__(self, outcome: ToolOutcome) -> None:
        """Store the canned outcome and start an empty call log."""
        self._outcome = outcome
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def call(
        self, server: str, tool: str, arguments: Mapping[str, Any]
    ) -> ToolOutcome:
        """Record ``(server, tool, arguments)`` and return the canned outcome."""
        self.calls.append((server, tool, dict(arguments)))
        return self._outcome


class RaisingInvoker:
    """A :class:`SubServerInvoker` whose ``call`` raises, to drive the
    orchestrators' generic exception boundary."""

    def __init__(self, exc: Exception) -> None:
        """Store the exception ``call`` should raise."""
        self._exc = exc

    async def call(
        self, server: str, tool: str, arguments: Mapping[str, Any]
    ) -> ToolOutcome:
        """Raise the stored exception unconditionally."""
        raise self._exc


@pytest.fixture
def valid_invoker() -> FakeInvoker:
    """A fake invoker whose base validator reports the payload valid."""
    return FakeInvoker(ToolOutcome(ok=True, data={"valid": True}))


@pytest.fixture
def make_invoker():
    """Return a factory building a :class:`FakeInvoker` from an outcome."""

    def _make(outcome: ToolOutcome) -> FakeInvoker:
        """Build a :class:`FakeInvoker` returning ``outcome``."""
        return FakeInvoker(outcome)

    return _make
