"""Unit tests for TenantConfig override precedence."""
from app.tenants import TenantConfig


def test_precedence_request_over_tenant_over_default():
    tc = TenantConfig()
    tc.set_overrides("t1", {"asset_params": {"orientation": "LR", "max_nodes": 10}})
    resolved = tc.resolve(
        "t1",
        manifest_defaults={"orientation": "TD", "max_nodes": 15},
        request_params={"max_nodes": 5},
    )
    assert resolved["orientation"] == "LR"   # tenant beats default
    assert resolved["max_nodes"] == 5        # request beats tenant


def test_no_overrides_returns_defaults():
    tc = TenantConfig()
    resolved = tc.resolve("unknown", {"orientation": "TD"})
    assert resolved == {"orientation": "TD"}
