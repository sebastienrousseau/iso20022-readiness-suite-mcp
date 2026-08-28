#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""What simulating a bank response costs.

This server exists so a migration team can rehearse against a bank that has
not switched on yet. Rehearsal means volume: a test harness replays a whole
batch through ``simulate_bank_response`` to see what comes back, and a real
batch is hundreds of ``<PmtInf>`` blocks rather than the single one in the
fixtures.

Three things are measured:

* **Cost against payload size.** Read ``us/block``. Flat means linear —
  total cost tracks payload size, because the whole inbound document is
  parsed. That is defensible, though a pacs.002 needs only the group header
  and the references, so there is room to read less. The defect to watch
  for is this number *climbing*, which would mean something re-walks what
  it has already read.

* **The three behaviours against each other.** ``ACCP``, ``RJCT`` and
  ``PDNG`` build different responses, so they should differ a little. A
  large gap would mean one path does markedly more work — worth knowing
  before a harness that replays thousands of rejections concludes the
  server is slow.

* **The rejected-argument path.** ``RJCT`` without a reason code is
  refused. Refusal should be the cheapest thing here: a validation error
  that first builds the response and then throws it away wastes the work on
  exactly the input a fuzzing harness sends most of.

Run::

    python benches/bench_simulate_response.py
    python benches/bench_simulate_response.py --json
    python benches/bench_simulate_response.py --quick     # what CI runs

Nothing here asserts a threshold: wall-clock is not comparable between
machines, and a flaky performance gate teaches people to ignore red. CI
runs ``--quick`` so a benchmark that has stopped compiling against the
current API fails the build instead of rotting into a file that reads as
verified and is not.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from iso20022_readiness_suite_mcp import server  # noqa: E402

HEAD = (
    '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.09">'
    "<CstmrCdtTrfInitn><GrpHdr><MsgId>PMT-BENCH</MsgId></GrpHdr>"
)
BLOCK = (
    "<PmtInf><PmtInfId>PI-{i}</PmtInfId><Cdtr><Nm>Payee {i}</Nm>"
    "<PstlAdr><TwnNm>London</TwnNm><Ctry>GB</Ctry></PstlAdr></Cdtr>"
    "</PmtInf>"
)
TAIL = "</CstmrCdtTrfInitn></Document>"


def build(blocks: int) -> str:
    """A pain.001 carrying ``blocks`` payment-information blocks."""
    return HEAD + "".join(BLOCK.format(i=i) for i in range(blocks)) + TAIL


def _best(call, repeats: int) -> float:
    """Best-of timing after one untimed warm-up.

    The minimum is the least noisy estimator available; the mean follows
    whatever else the machine happens to be doing.
    """
    call()
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        call()
        samples.append(time.perf_counter() - start)
    return min(samples)


def measure_size(blocks: int, repeats: int) -> dict:
    payload = build(blocks)
    best = _best(
        lambda: server.simulate_bank_response(payload, "ACCP"), repeats
    )
    return {
        "case": "by size",
        "blocks": blocks,
        "bytes": len(payload),
        "ms": best * 1e3,
        "us_per_block": best * 1e6 / blocks,
    }


def measure_behaviours(blocks: int, repeats: int) -> list[dict]:
    """The three outcomes, plus the refusal path."""
    payload = build(blocks)
    cases = [
        ("ACCP", None),
        ("RJCT", "AM04"),
        ("PDNG", None),
        ("RJCT", None),  # refused: RJCT requires a reason code
    ]
    rows = []
    for behaviour, reason in cases:

        def call(behaviour=behaviour, reason=reason):
            try:
                return server.simulate_bank_response(
                    payload, behaviour, reason_code=reason
                )
            except Exception:
                # A refusal is a result, not an error. How quickly it
                # refuses is exactly what is being measured.
                return None

        best = _best(call, repeats)
        rows.append(
            {
                "case": "by behaviour",
                "behaviour": behaviour,
                "reason_code": reason,
                "refused": behaviour == "RJCT" and reason is None,
                "blocks": blocks,
                "ms": best * 1e3,
            }
        )
    return rows


def run(quick: bool) -> dict:
    sizes = [10, 100] if quick else [10, 100, 1_000, 5_000]
    repeats = 3 if quick else 7
    return {
        "size": [measure_size(n, repeats) for n in sizes],
        "behaviours": measure_behaviours(sizes[1], repeats),
    }


def render(results: dict) -> None:
    print("simulate_bank_response(ACCP), by payload size")
    print(f"{'blocks':>8}{'KiB':>9}{'ms':>10}{'us/block':>11}")
    for row in results["size"]:
        print(
            f"{row['blocks']:>8}{row['bytes'] / 1024:>9.1f}"
            f"{row['ms']:>10.3f}{row['us_per_block']:>11.2f}"
        )
    rows = results["size"]
    if len(rows) >= 2 and rows[0]["us_per_block"]:
        drift = rows[-1]["us_per_block"] / rows[0]["us_per_block"]
        print(
            f"  us/block at {rows[-1]['blocks']:,} is {drift:.2f}x the cost "
            f"at {rows[0]['blocks']:,}. Near 1.00 means linear: total cost "
            f"tracks payload size, so the simulator parses the whole inbound "
            f"document. That is defensible — but a pacs.002 needs only the "
            f"group header and the references, so a future version could "
            f"read less. What would be a defect is this number climbing."
        )

    print("\nby behaviour, same payload")
    print(f"{'behaviour':>11}{'reason':>9}{'refused':>9}{'ms':>10}")
    for row in results["behaviours"]:
        print(
            f"{row['behaviour']:>11}{str(row['reason_code']):>9}"
            f"{str(row['refused']):>9}{row['ms']:>10.4f}"
        )
    refused = [r for r in results["behaviours"] if r["refused"]]
    accepted = [r for r in results["behaviours"] if not r["refused"]]
    if refused and accepted:
        cheapest = min(r["ms"] for r in accepted)
        print(
            f"\n  Refusing RJCT-without-a-reason costs "
            f"{refused[0]['ms']:.4f} ms against {cheapest:.4f} ms for the "
            f"cheapest real response. Refusal should be the cheaper path: "
            f"validation that builds a response first and then discards it "
            f"wastes the work on exactly the input a fuzzing harness sends "
            f"most of."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--quick", action="store_true", help="small sizes, as CI runs"
    )
    args = parser.parse_args()

    results = run(quick=args.quick)
    if args.json:
        json.dump(results, sys.stdout, indent=1)
        print()
    else:
        render(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
