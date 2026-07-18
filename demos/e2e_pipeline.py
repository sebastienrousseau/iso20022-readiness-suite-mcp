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

"""End-to-end proof that the ISO 20022 orchestration suite composes for real.

This is NOT a unit test and NOT part of the CI harness: it launches the three
PUBLISHED orchestration servers as separate real subprocesses over stdio (via
``uvx``, so it needs network access on first run and pulls them from PyPI) and
drives them through one pipeline. Nothing is stubbed.

    readiness-suite.run_readiness_check   the meta-client: itself an MCP client
                                          that spawns camt053-mcp via uvx for
                                          structural validation, then profile-
                                          lints and scores
        -> bank-profile.lint_payload      clearing-profile (CBPR+) findings
        -> evidence-pack.build_evidence_pack + seal + Ed25519 sign + verify

Run it:  ``python demos/e2e_pipeline.py`` (in an env with ``mcp`` and
``cryptography`` installed, e.g. ``poetry run python demos/e2e_pipeline.py``).
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# A minimal camt.053 bank-to-customer statement whose debtor postal address is
# missing a country element -- the CBPR+ profile flags it.
CAMT053 = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08">
  <BkToCstmrStmt>
    <GrpHdr><MsgId>E2E-DEMO-1</MsgId>
      <CreDtTm>2026-07-18T00:00:00</CreDtTm></GrpHdr>
    <Stmt>
      <Id>STMT-1</Id>
      <Acct><Id><IBAN>DE89370400440532013000</IBAN></Id></Acct>
      <Ntry>
        <Amt Ccy="EUR">100.00</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <NtryDtls><TxDtls><RltdPties><Dbtr><Nm>ACME GmbH</Nm>
          <PstlAdr><StrtNm>Hauptstrasse</StrtNm><TwnNm>Berlin</TwnNm></PstlAdr>
        </Dbtr></RltdPties></TxDtls></NtryDtls>
      </Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>
"""


def _text(result: Any) -> Any:
    """Extract and JSON-decode the first text block of a tool result."""
    for item in result.content:
        text = getattr(item, "text", None)
        if text is not None:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
    return None


async def _call(
    server: str,
    tool: str,
    args: dict[str, Any],
    env: dict[str, str] | None = None,
) -> Any:
    """Spawn ``uvx <server>`` over stdio and call one tool, returning data."""
    params = StdioServerParameters(command="uvx", args=[server], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return _text(await session.call_tool(tool, args))


async def main() -> None:
    """Drive the three servers through the readiness -> evidence pipeline."""
    print("STEP 1 - readiness-suite (meta-client) run_readiness_check")
    readiness = await _call(
        "iso20022-readiness-suite-mcp",
        "run_readiness_check",
        {"payload_content": CAMT053, "target_profile": "CBPR+"},
    )
    print(
        f"  message_type={readiness.get('message_type')!r} "
        f"is_valid={readiness.get('is_valid')} "
        f"score={readiness.get('readiness_score')} "
        f"structural_errors={len(readiness.get('structural_errors', []))} "
        f"profile_findings={len(readiness.get('profile_findings', []))}"
    )

    print("STEP 2 - bank-profile lint_payload (CBPR+)")
    lint = await _call(
        "iso20022-bank-profile-mcp",
        "lint_payload",
        {"payload_content": CAMT053, "profile_id": "CBPR+"},
    )
    print(
        f"  is_compliant={lint.get('is_compliant')} "
        f"findings={[f['code'] for f in lint.get('findings', [])]}"
    )

    print("STEP 3 - evidence-pack build_evidence_pack + seal")
    build = await _call(
        "iso20022-evidence-pack-mcp",
        "build_evidence_pack",
        {
            "readiness_content": json.dumps(readiness),
            "metadata": {"institution": "Demo Bank", "reference": "E2E-1"},
        },
    )
    pack = build["pack"]
    print(f"  grade={pack['grade']} digest={build['digest'][:24]}...")

    print("STEP 4 - evidence-pack Ed25519 sign + verify")
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    sign_env = {**os.environ, "ISO20022_EVIDENCE_PACK_SIGNING_KEY": pem}
    signed = await _call(
        "iso20022-evidence-pack-mcp",
        "sign_pack",
        {"pack_content": json.dumps(pack)},
        env=sign_env,
    )
    print(
        f"  algorithm={signed['algorithm']} key_id={signed['key_id']} "
        f"sig_len={len(signed['signature'])}"
    )
    verify = await _call(
        "iso20022-evidence-pack-mcp",
        "verify_pack_signature",
        {
            "pack_content": json.dumps(pack),
            "signature": signed["signature"],
            "public_key": signed["public_key"],
        },
    )
    print(f"  verified={verify['verified']} key_id={verify['key_id']}")

    ok = (
        str(readiness.get("message_type", "")).startswith("camt.05")
        and bool(lint.get("findings"))
        and bool(verify.get("verified"))
    )
    status = "OK" if ok else "FAILED"
    print(
        f"\nPIPELINE {status}: readiness -> profile lint -> "
        "sealed + signed evidence pack"
    )


if __name__ == "__main__":
    asyncio.run(main())
