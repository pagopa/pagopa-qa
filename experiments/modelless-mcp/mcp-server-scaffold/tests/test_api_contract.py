"""Contract/integration tests for the REST control plane using FastAPI TestClient.

Auth is disabled via MCP_AUTH_DISABLED=1 so these run without Azure AD locally.
"""
import os

os.environ["MCP_AUTH_DISABLED"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_health_is_public():
    r = client.get("/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_list_assets_contains_mermaid():
    r = client.get("/v1/assets")
    assert r.status_code == 200
    ids = {a["id"] for a in r.json()}
    assert "mermaid-flow" in ids


def test_search_assets_by_query():
    r = client.get("/v1/assets", params={"q": "mermaid"})
    assert r.status_code == 200
    ids = {a["id"] for a in r.json()}
    assert "mermaid-flow" in ids

    empty = client.get("/v1/assets", params={"q": "no-such-asset-xyz"})
    assert empty.status_code == 200
    assert empty.json() == []


def test_get_asset_manifest():
    r = client.get("/v1/assets/mermaid-flow")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "mermaid-flow"
    assert body["digest"].startswith("sha256:")
    assert body["install"]["target_path"] == ".github/skills/mermaid-flow/SKILL.md"


def test_install_descriptor_anchors_version_and_digest():
    r = client.get("/v1/assets/mermaid-flow/install")
    assert r.status_code == 200
    body = r.json()
    assert body["source_version"] == "1.0.0"
    assert body["source_digest"].startswith("sha256:")
    assert body["target_path"] == ".github/skills/mermaid-flow/SKILL.md"
    # Provenance/version anchors are written into the installed file's frontmatter.
    assert "source: mcp-catalog" in body["content"]
    assert "source_version: 1.0.0" in body["content"]
    assert body["source_digest"] in body["content"]


def test_get_unknown_asset_404():
    assert client.get("/v1/assets/does-not-exist").status_code == 404
    assert client.get("/v1/assets/does-not-exist/install").status_code == 404


def test_tenant_override_roundtrip():
    put = client.put(
        "/v1/tenants/tenant-x/overrides",
        json={"asset_params": {"orientation": "LR"}},
    )
    assert put.status_code == 200
    get = client.get("/v1/tenants/tenant-x/overrides")
    assert get.status_code == 200
    assert get.json()["asset_params"]["orientation"] == "LR"

