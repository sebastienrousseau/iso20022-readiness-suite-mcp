# syntax=docker/dockerfile:1.6
# Multi-stage build for a minimal iso20022-readiness-suite-mcp image.
#
# The container runs the FastMCP orchestration server over stdio so an MCP
# client can launch it directly with
# ``docker run -i --rm iso20022-readiness-suite-mcp``.
#
# NOTE: this image bundles ONLY the orchestration server. The foundational
# suite servers it delegates to (iso20022-mcp, camt053-mcp, pain001-mcp,
# reconcile-mcp, bankstatementparser-mcp, structured-address-fix-mcp) are NOT
# installed here. ``list_profiles`` and ``simulate_bank_response`` work
# standalone; ``run_readiness_check`` and ``remediate_payload`` spawn the
# underlying servers via ``uvx`` and therefore need them resolvable in the
# runtime environment (mount a populated uv cache, extend this image, or run
# the sub-servers as sidecars).

FROM python:3.14-slim@sha256:d3400aa122fa42cf0af0dbe8ec3091b047eac5c8f7e3539f7135e86d855dc015 AS builder

WORKDIR /build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# pyproject.toml carries ``readme = "README.md"``, so README.md must be
# present at build-time for ``pip install .`` to resolve the package
# metadata. The bundled clearing-profile JSON ships inside the package tree.
COPY pyproject.toml README.md ./
COPY iso20022_readiness_suite_mcp ./iso20022_readiness_suite_mcp

# Install this package (and its published runtime deps: mcp, pydantic,
# defusedxml) into a self-contained virtualenv.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install .


FROM python:3.14-slim@sha256:d3400aa122fa42cf0af0dbe8ec3091b047eac5c8f7e3539f7135e86d855dc015

LABEL org.opencontainers.image.title="iso20022-readiness-suite-mcp" \
      org.opencontainers.image.description="Orchestration MCP server for ISO 20022 readiness scoring, remediation, and bank-response simulation over the foundational MCP servers." \
      org.opencontainers.image.source="https://github.com/sebastienrousseau/iso20022-readiness-suite-mcp" \
      org.opencontainers.image.licenses="Apache-2.0"

# Non-root user (MCP clients launch the container with stdio; no extra
# privileges needed).
RUN groupadd --system mcp && useradd --system --gid mcp --home /home/mcp mcp \
    && mkdir -p /home/mcp \
    && chown -R mcp:mcp /home/mcp

COPY --from=builder /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER mcp
WORKDIR /home/mcp

# A non-zero exit here means an import / dependency mismatch; the MCP
# client will see it before the first tool call.
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import iso20022_readiness_suite_mcp.server" || exit 1

ENTRYPOINT ["iso20022-readiness-suite-mcp"]
