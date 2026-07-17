"""Tenant configuration and deterministic override resolution.

Override precedence (low -> high):
    manifest default  <  tenant override  <  request-time parameter
"""
from __future__ import annotations

from typing import Any


class TenantConfig:
    def __init__(self) -> None:
        # In-memory store for the MVP; production uses Postgres/Cosmos.
        self._overrides: dict[str, dict[str, Any]] = {}

    def set_overrides(self, tenant_id: str, overrides: dict[str, Any]) -> None:
        self._overrides[tenant_id] = overrides

    def get_overrides(self, tenant_id: str) -> dict[str, Any]:
        return self._overrides.get(tenant_id, {})

    def resolve(
        self,
        tenant_id: str,
        manifest_defaults: dict[str, Any],
        request_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        merged: dict[str, Any] = dict(manifest_defaults)
        merged.update(self.get_overrides(tenant_id).get("asset_params", {}))
        if request_params:
            merged.update(request_params)
        return merged
