"""Contract tests for the MCP JSON-RPC endpoint (`/mcp`), the ephemeral load surface.

Auth is disabled via MCP_AUTH_DISABLED=1 so these run without Azure AD locally.
"""
import json
import os

os.environ["MCP_AUTH_DISABLED"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def _rpc(method: str, params: dict | None = None, id_: int | None = 1) -> dict:
    body = {"jsonrpc": "2.0", "method": method}
    if id_ is not None:
        body["id"] = id_
    if params is not None:
        body["params"] = params
    return body


def test_initialize_returns_protocol_and_capabilities():
    r = client.post("/mcp", json=_rpc("initialize"))
    assert r.status_code == 200
    result = r.json()["result"]
    assert "protocolVersion" in result
    assert "resources" in result["capabilities"]
    assert "prompts" in result["capabilities"]


def test_initialized_notification_has_no_body():
    r = client.post("/mcp", json=_rpc("notifications/initialized", id_=None))
    assert r.status_code == 204


def test_resources_list_contains_mermaid_flow():
    r = client.post("/mcp", json=_rpc("resources/list"))
    assert r.status_code == 200
    uris = {res["uri"] for res in r.json()["result"]["resources"]}
    assert "catalog://mermaid-flow" in uris


def test_resources_read_returns_raw_body_not_anchored():
    r = client.post("/mcp", json=_rpc("resources/read", {"uri": "catalog://mermaid-flow"}))
    assert r.status_code == 200
    contents = r.json()["result"]["contents"]
    assert len(contents) == 1
    assert contents[0]["uri"] == "catalog://mermaid-flow"
    # Ephemeral load: no provenance/version anchoring (that's install-only).
    assert "source: mcp-catalog" not in contents[0]["text"]


def test_resources_read_unknown_uri_is_jsonrpc_error():
    r = client.post("/mcp", json=_rpc("resources/read", {"uri": "catalog://does-not-exist"}))
    assert r.status_code == 200
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] == -32002


def test_unknown_method_is_method_not_found():
    r = client.post("/mcp", json=_rpc("not/a/real-method"))
    assert r.status_code == 200
    assert r.json()["error"]["code"] == -32601


def test_initialize_advertises_tools_capability():
    r = client.post("/mcp", json=_rpc("initialize"))
    assert "tools" in r.json()["result"]["capabilities"]


def test_tools_list_contains_search_and_install():
    r = client.post("/mcp", json=_rpc("tools/list"))
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert names == {"search_assets", "install_asset"}


def test_tools_call_search_assets_returns_summary():
    r = client.post("/mcp", json=_rpc("tools/call", {"name": "search_assets", "arguments": {"query": "mermaid"}}))
    assert r.status_code == 200
    result = r.json()["result"]
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    ids = {entry["id"] for entry in payload}
    assert "mermaid-flow" in ids


def test_tools_call_install_asset_returns_anchored_descriptor():
    r = client.post("/mcp", json=_rpc("tools/call", {"name": "install_asset", "arguments": {"asset_id": "mermaid-flow"}}))
    assert r.status_code == 200
    result = r.json()["result"]
    assert result["isError"] is False
    descriptor = json.loads(result["content"][0]["text"])
    assert descriptor["target_path"] == ".github/skills/mermaid-flow/SKILL.md"
    assert "source: mcp-catalog" in descriptor["content"]


def test_tools_call_install_asset_unknown_id_is_tool_error_not_rpc_error():
    r = client.post("/mcp", json=_rpc("tools/call", {"name": "install_asset", "arguments": {"asset_id": "does-not-exist"}}))
    assert r.status_code == 200
    result = r.json()["result"]
    assert result["isError"] is True


def test_tools_call_unknown_tool_name_is_jsonrpc_error():
    r = client.post("/mcp", json=_rpc("tools/call", {"name": "not_a_tool", "arguments": {}}))
    assert r.status_code == 200
    assert r.json()["error"]["code"] == -32602
