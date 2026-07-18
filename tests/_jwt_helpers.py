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

"""Shared crypto/JWT helpers for the HTTP OAuth tests.

Generates throwaway RSA keypairs, builds JWKS entries and PyJWK cache
values, and signs RS256 JWTs so the OAuth resource-server code can be
exercised end-to-end with real signatures but no network access.
"""

from __future__ import annotations

import time
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def make_keypair() -> tuple[rsa.RSAPrivateKey, str]:
    """Return a fresh RSA private key and its PKCS#8 PEM encoding."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return key, pem


def jwks_entry(key: rsa.RSAPrivateKey, kid: str = "k1") -> dict[str, Any]:
    """Build a signing JWKS entry (with ``kid`` / ``use``) for ``key``."""
    entry = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    entry["kid"] = kid
    entry["use"] = "sig"
    return entry


def pyjwk(key: rsa.RSAPrivateKey, kid: str = "k1") -> jwt.PyJWK:
    """Build the :class:`jwt.PyJWK` cache value for ``key``."""
    return jwt.PyJWK(jwks_entry(key, kid))


def sign(
    pem: str,
    *,
    issuer: str = "https://issuer.example.com",
    audience: str = "https://mcp.example.com/mcp",
    kid: str = "k1",
    expires_in: int = 3600,
    scope: str | None = None,
    include_exp: bool = True,
    extra: dict[str, Any] | None = None,
) -> str:
    """Sign an RS256 JWT with the given claims and ``kid`` header."""
    now = int(time.time())
    claims: dict[str, Any] = {"iss": issuer, "aud": audience}
    if include_exp:
        claims["exp"] = now + expires_in
    if scope is not None:
        claims["scope"] = scope
    if extra:
        claims.update(extra)
    return jwt.encode(claims, pem, algorithm="RS256", headers={"kid": kid})
