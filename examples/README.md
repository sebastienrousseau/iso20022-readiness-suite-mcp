# iso20022-readiness-suite-mcp examples

Runnable, self-contained examples for the ISO 20022 readiness suite MCP
server. Each script drives the public tools or orchestrators directly.
Run any of them from the repository root:

```sh
python examples/<name>.py
```

| Example | Focus | Sub-server |
|---------|-------|------------|
| [`01_list_profiles.py`](01_list_profiles.py) | Discover the clearing profiles (`target_profile` values) | none |
| [`02_detect_and_route.py`](02_detect_and_route.py) | Detect a message type and see which server validates it | none |
| [`03_readiness_check.py`](03_readiness_check.py) | End-to-end readiness scoring against CBPR+ | **stub** invoker |
| [`04_remediate_payload.py`](04_remediate_payload.py) | Automated structured-address remediation | **stub** invoker |
| [`05_simulate_accept.py`](05_simulate_accept.py) | Generate an accepted (ACCP) pacs.002 | none (local) |
| [`06_simulate_reject.py`](06_simulate_reject.py) | Generate a rejection (RJCT) with a reason code | none (local) |
| [`07_apply_profile.py`](07_apply_profile.py) | Lint a payload against a clearing profile | none |
| [`08_score_and_summary.py`](08_score_and_summary.py) | Score findings and render an evidence summary | none |
| [`09_http_oauth_config.py`](09_http_oauth_config.py) | The HTTP transport's OAuth 2.1 (RFC 9728) config + metadata | none |

## Stub sub-servers

`run_readiness_check` and `remediate_payload` normally reach the
foundational MCP servers (`pain001-mcp`, `structured-address-fix-mcp`, …)
over stdio. So the readiness and remediate examples stay **offline and
deterministic**, they inject a small **stub invoker** in place of the real
`StdioSubServerInvoker` — it returns a canned outcome without spawning any
sub-process. Each of those two scripts documents this in its module
docstring. Every other example is fully local and needs no sub-server.

## Installation

The examples import from `iso20022_readiness_suite_mcp`, so install the
package first (Python 3.10+):

```sh
pip install iso20022-readiness-suite-mcp
```

When running from a checkout without installing, put the repository root
on `PYTHONPATH`:

```sh
PYTHONPATH=. python examples/03_readiness_check.py
```
