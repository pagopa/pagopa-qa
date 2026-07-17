"""Minimal Azure AD (Entra ID) auth dependency for FastAPI.

For the MVP / local dev this validates the presence of a Bearer token and extracts
a tenant claim. In production, replace `_decode` with real JWKS signature/audience
validation (e.g. via `azure-identity` + `PyJWT` and the Entra ID JWKS endpoint).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import Header, HTTPException, status


@dataclass
class Principal:
    tenant_id: str
    subject: str
    roles: list[str]


def _decode(token: str) -> Principal:
    # DEV-ONLY placeholder. DO NOT use in production.
    # Expected dev token format: "dev.<tenant_id>.<subject>.<role>"
    parts = token.split(".")
    if len(parts) >= 4 and parts[0] == "dev":
        return Principal(tenant_id=parts[1], subject=parts[2], roles=[parts[3]])
    # Fallback dev principal
    return Principal(tenant_id="tenant-local", subject="local-user", roles=["user"])


async def get_principal(authorization: str | None = Header(default=None)) -> Principal:
    if os.environ.get("MCP_AUTH_DISABLED") == "1":
        return Principal(tenant_id="tenant-local", subject="local-user", roles=["admin"])
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    token = authorization.split(" ", 1)[1]
    return _decode(token)


def require_role(principal: Principal, role: str) -> None:
    if role not in principal.roles and "admin" not in principal.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requires role: {role}",
        )
