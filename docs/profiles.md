# Clearing profiles

A **clearing profile** captures the market-practice assertions that lie
*beyond* structural XSD validation — the scheme-specific rules a payment
must satisfy to clear. `iso20022-readiness-suite-mcp` ships a small set
of open baseline profiles and lets premium rule packs plug in at
runtime through the same engine.

Discover the profiles an installation offers with the `list_profiles`
tool; pass a profile's `profile_id` as the `target_profile` argument to
`run_readiness_check` and `remediate_payload`.

## The bundled (open-source) profiles

| `profile_id` | Market practice | Supported messages | Baseline rules |
| --- | --- | --- | --- |
| `Generic` | ISO 20022 baseline | (all) | None beyond structural validation — the default. |
| `CBPR+` | SWIFT CBPR+ UG2026 | pacs.008, pacs.009, pain.001 | Every postal address must carry a `Ctry` (country) and a `TwnNm` (town) element from the Nov 2026 cliff. |
| `SEPA_Instant` | SEPA SCT Inst | pacs.008, pain.001 | For EUR payments the charge bearer (`ChrgBr`) must be `SLEV`. |
| `FedNow` | FedNow Core | pacs.008, pacs.002 | FedNow requires a structured `Ctry` element on party addresses. |

`Generic` is intentionally empty: it applies only the structural
validation performed by the routed base validator, with no extra
market-practice assertions. It is the default `target_profile` for
`run_readiness_check`. `CBPR+` is the default for `remediate_payload`,
since the Nov 2026 structured-address rules are what remediation most
often targets.

## How a profile is evaluated

Profiles are **pure data** — bundled JSON for the open baseline, loadable
at runtime for premium packs. The `ProfileEngine` loads them, then
evaluates each rule against a payload parsed with `defusedxml` only.

Each rule is a small declarative assertion:

| Assertion form | Meaning |
| --- | --- |
| `required` | The `locator` element must be present somewhere in the payload. |
| `equals:<value>` | The `locator` element's text must equal `<value>`. |
| `if:<elem>=<val>:equals:<val2>` | Conditional: only when `<elem>` equals `<val>`, the `locator` element's text must equal `<val2>`. |

A rule that is violated produces a finding — a typed `ErrorDetail`
carrying its `error_code`, the `locator` it inspected, a human-readable
explanation, and the rule's `severity` (`info` / `warning` / `error`).
`run_readiness_check` folds those findings into the payload's readiness
score; a compliant payload yields no findings.

A bundled profile is just a JSON document, e.g. the SEPA Instant EUR
charge-bearer rule:

```json
{
  "profile_id": "SEPA_Instant",
  "market_practice": "SEPA SCT Inst",
  "supported_messages": ["pacs.008", "pain.001"],
  "custom_rules": [
    {
      "rule_id": "sepa-eur-slev",
      "description": "For EUR payments the charge bearer (ChrgBr) must be SLEV.",
      "locator": "ChrgBr",
      "assertion": "if:Ccy=EUR:equals:SLEV",
      "error_code": "SEPA_CHRGBR_NOT_SLEV",
      "severity": "error"
    }
  ]
}
```

## How premium rule packs plug in

The engine exposes two seams:

- `ProfileEngine.from_bundled()` loads the open baseline profiles that
  ship inside the package (`data/profiles/*.json`). This is what the
  shipped console script uses.
- `ProfileEngine.register(profile)` registers (or replaces) a profile at
  runtime — the extension point for **premium, institution-specific rule
  packs**.

A premium pack is the *same shape* as a bundled profile: a
`ClearingProfile` with a `profile_id`, a `market_practice`, its
`supported_messages`, and a list of `custom_rules`. A deployment that
embeds the gateway can build an engine, register its licensed packs, and
serve them alongside the open baseline:

```python
from iso20022_readiness_suite_mcp.policies.engine import ProfileEngine
from iso20022_readiness_suite_mcp.models import ClearingProfile

engine = ProfileEngine.from_bundled()      # open baseline
engine.register(                           # premium / bank-specific pack
    ClearingProfile.model_validate(my_bank_profile_json)
)
```

Once registered, a pack's `profile_id` appears in `list_profiles` and is
accepted as a `target_profile` by `run_readiness_check` and
`remediate_payload` — the tool surface does not change.

On the [roadmap](https://github.com/sebastienrousseau/iso20022-readiness-suite-mcp/blob/main/ROADMAP.md), the higher-tier packs are gated behind
an **entitlement claim** (so operators license the scheme packs they
need), and a sister `iso20022-bank-profile-mcp` server will manage and
serve bank-specific packs as a first-class server the gateway consumes.
Everything in the open-source tier — the four bundled profiles and the
engine itself — is unrestricted and not feature-gated.

## Choosing a profile

- **Cross-border / correspondent banking:** `CBPR+`.
- **Euro instant payments:** `SEPA_Instant`.
- **US instant payments:** `FedNow`.
- **Structural validation only, no scheme rules:** `Generic` (the
  default).

When in doubt, call `list_profiles` first to see exactly what an
installation offers, then run `run_readiness_check` with each candidate
profile and compare the scores.
