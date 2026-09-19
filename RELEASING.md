<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# Releasing iso20022-readiness-suite-mcp

This document defines **what merits a release** and **how to cut one**,
so versions are deliberate rather than ad-hoc.

## Versioning scheme

iso20022-readiness-suite-mcp is versioned on its own `0.0.X` line; it
does not move in lockstep with the foundational servers it orchestrates,
because it talks to them over MCP rather than importing them. A change
in a sub-server's tool surface that the gateway depends on is a change
here too, and gets its own release.

## What merits a release

Cut a new version when there is user-visible change to ship - bug fixes,
security or dependency patches, new tools / resources / prompts / clearing
profiles, a transport change, or documentation that ships in the package.

## Pre-flight checklist

A release is ready only when **all** of the following hold on `main`:

1. `make check` is green (lint + type-check + tests at 100% line and
   branch coverage), and `make examples` runs every script in
   `examples/`.
2. `interrogate` reports 100% docstring coverage; `mypy --strict`,
   `ruff`, `black` are clean on `iso20022_readiness_suite_mcp/`, `tests/`
   and `benches/`.
3. Every Dependabot / CodeQL / bandit alert is resolved or has a
   documented, expiring suppression.
4. `CHANGELOG.md` has a dated section for the new version describing the
   change set (this is the single source of truth for the release).
5. The version is identical in `pyproject.toml`,
   `iso20022_readiness_suite_mcp/__init__.py`, `glama.json` (including
   its Docker tag), `server.json`, `CITATION.cff` and the changelog
   (`scripts/verify_versions.py`, run by the `Version sources agree`
   workflow, checks all but the citation). The Glama directory and the
   MCP registry read those two manifests; a release that forgets them
   shows an old version to every agent that browses for the server.
6. `poetry.lock` is current: the `Lockfile matches pyproject` job fails
   on a stale lock, and `requirements/*.txt` are regenerated with
   `make pip-compile` when a dependency floor moves.

## Cutting the release

1. Bump the version in `pyproject.toml`,
   `iso20022_readiness_suite_mcp/__init__.py`, `glama.json`,
   `server.json` and `CITATION.cff`, and add the `CHANGELOG.md` section,
   in a single PR.
2. Merge the PR to `main` once CI is green.
3. Push a signed tag:

   ```bash
   git tag -s vX.Y.Z -m "iso20022-readiness-suite-mcp vX.Y.Z" <merge-commit>
   git push origin vX.Y.Z
   ```

4. The tag triggers `release.yml`: it builds the distributions, runs
   `twine check`, attaches a SLSA build provenance attestation,
   publishes to PyPI through OIDC trusted publishing with PEP 740
   attestations, signs the distributions with cosign (keyless) and
   publishes the GitHub release with the artifacts. A second job
   produces the CycloneDX and SPDX SBOMs and the licence report.
5. The same tag triggers `publish-mcp.yml`, which publishes
   `server.json` to the official MCP registry through GitHub OIDC.

## After releasing

- Confirm the version is live on
  [PyPI](https://pypi.org/project/iso20022-readiness-suite-mcp/) and the
  GitHub release is published (not draft), with the SBOMs attached.
- Verify a clean install:
  `pip install iso20022-readiness-suite-mcp==X.Y.Z`.
- Check the [MCP registry](https://registry.modelcontextprotocol.io)
  and Glama listings show the new version.
- The scheduled `Release Consistency` workflow compares the tree with
  PyPI; a tree ahead of the index between the merge and the tag is the
  expected transient, a tree behind it is not.

## Optional CI integrations

These are deliberately gated so an empty / un-set secret skips the
step rather than failing the build:

- **PyPI trusted publisher** (`release.yml`): configured at
  <https://pypi.org/manage/account/publishing/>. The publisher claim
  set is `repo:sebastienrousseau/iso20022-readiness-suite-mcp:environment:pypi`
  with `workflow_ref` pointing at `.github/workflows/release.yml`.
- **MCP registry publisher** (`publish-mcp.yml`): `mcp-publisher login
  github-oidc`; no secret to store.
- **Docker image**: the `Dockerfile` builds the server for a container
  deployment; images are not published by CI.
