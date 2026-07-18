#!/usr/bin/env python3
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

"""Example: the optional HTTP transport's OAuth 2.1 configuration (RFC 9728).

Run the server over streamable HTTP with::

    ISO20022_READINESS_OAUTH_ISSUER=https://auth.example.com \\
    ISO20022_READINESS_OAUTH_AUDIENCE=https://mcp.example.com/mcp \\
    iso20022-readiness-suite-mcp --transport=http --bind=0.0.0.0:8080

This example resolves that configuration from an environment mapping and shows
the RFC 9728 protected-resource metadata the server publishes, without opening
a socket. (stdio remains the default transport and needs no auth.)

Usage::

    python examples/09_http_oauth_config.py
"""

import json

from iso20022_readiness_suite_mcp.http import oauth

_ENV = {
    "ISO20022_READINESS_OAUTH_ISSUER": "https://auth.example.com",
    "ISO20022_READINESS_OAUTH_AUDIENCE": "https://mcp.example.com/mcp",
    "ISO20022_READINESS_OAUTH_SCOPES": "readiness:read",
}


def main() -> None:
    """Resolve the OAuth config and render the RFC 9728 metadata."""
    config = oauth.OAuthConfig.from_env(_ENV)
    assert config is not None  # both issuer and audience are set
    print(f"issuer   = {config.issuer}")
    print(f"audience = {config.audience}")
    print(f"jwks_url = {config.jwks_url}  (defaulted from the issuer)")
    print(f"required_scopes = {list(config.required_scopes)}")

    metadata_url = oauth.resource_metadata_url(config.audience)
    print(f"\nprotected-resource metadata served at:\n  {metadata_url}")
    print(
        "metadata document:\n"
        + json.dumps(oauth.protected_resource_metadata(config), indent=2)
    )

    # With no ISO20022_READINESS_OAUTH_* set, from_env returns None and the
    # transport falls back to the static dev-mode token.
    print(
        f"\nfrom_env({{}}) with nothing set -> {oauth.OAuthConfig.from_env({})}"
    )


if __name__ == "__main__":
    main()
