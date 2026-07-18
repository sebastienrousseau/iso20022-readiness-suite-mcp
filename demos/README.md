# Demos

Runnable, cross-server demonstrations of the **ISO 20022 MCP Suite** composing
end to end. Unlike [`examples/`](../examples/) — small, in-process, and part of
the CI coverage gate — the scripts here launch the **published** servers as
real subprocesses and are intentionally **not** run in CI (they need network
access and pull the servers from PyPI on first run).

## `e2e_pipeline.py` — the whole suite, for real

Drives the three orchestration servers through one pipeline, nothing stubbed:

```
readiness-suite.run_readiness_check   ← the meta-client: itself an MCP client
                                        that spawns camt053-mcp via uvx for
                                        structural validation, then profile-
                                        lints and scores a camt.053 statement
    → bank-profile.lint_payload        ← clearing-profile (CBPR+) findings
    → evidence-pack.build_evidence_pack + seal + Ed25519 sign + verify
```

Each server is a separate real process speaking MCP over stdio, launched with
[`uvx`](https://docs.astral.sh/uv/). The readiness-suite server is itself an
MCP **client** to `camt053-mcp` — the meta-client pattern exercised for real.

### Prerequisites

- [`uv` / `uvx`](https://docs.astral.sh/uv/) on `PATH`.
- Network access on first run (the servers are fetched from PyPI).
- An environment with `mcp` and `cryptography` installed (e.g. this repo's
  Poetry environment).

### Run

```bash
poetry run python demos/e2e_pipeline.py
```

Expected tail:

```
STEP 1 - readiness-suite (meta-client) run_readiness_check
  message_type='camt.053.001.08' is_valid=False score=0 structural_errors=4 profile_findings=1
STEP 2 - bank-profile lint_payload (CBPR+)
  is_compliant=False findings=['CBPR_MISSING_COUNTRY']
STEP 3 - evidence-pack build_evidence_pack + seal
  grade=F digest=sha256:...
STEP 4 - evidence-pack Ed25519 sign + verify
  algorithm=ed25519 key_id=ed25519:... sig_len=88
  verified=True key_id=ed25519:...

PIPELINE OK: readiness -> profile lint -> sealed + signed evidence pack
```

The sample `camt.053` statement omits a country element on the debtor's postal
address, so CBPR+ profile linting flags `CBPR_MISSING_COUNTRY` and the sealed,
signed evidence pack captures a grade-F readiness outcome.
