"""Minimal MCP (Model Context Protocol) JSON-RPC handler over Streamable HTTP.

This is the **ephemeral load** surface: it lets a real MCP client (e.g. VS Code)
connect, discover the catalog as `resources`, and read an asset's raw content into
the current chat/session context. It executes nothing and hosts no model — it only
serves versioned content already held by `AssetCatalog`. The **hard install** flow
(materializing an asset as a local file) stays on the REST control plane
(`GET /v1/assets/{id}/install`); this module does not write any file.

Supported methods (MVP subset, enough for VS Code to connect and read resources):
- `initialize`                 -> protocol handshake
- `notifications/initialized`  -> client notification, no response (per JSON-RPC)
- `ping`                       -> liveness
- `resources/list`             -> one resource per catalog asset (`catalog://{id}`)
- `resources/read`             -> raw asset body (ephemeral load, NOT anchored)
- `prompts/list` / `prompts/get` -> empty for the MVP (no prompt assets yet)
- `tools/list`                 -> catalog-backed tools (search, install descriptor)
- `tools/call`                 -> invoke one of the tools below

Tools (still modelless: they only read the in-memory catalog, they never write to
disk or call a model):
- `search_assets`  -> filtered catalog search (mirrors `GET /v1/assets`)
- `install_asset`  -> returns the anchored install descriptor for an asset (mirrors
  `GET /v1/assets/{id}/install`). The **client** is responsible for writing the
  returned `content` to `target_path` on its own local filesystem — the server
  itself never performs filesystem writes (no arbitrary path/write surface here).

See docs/learn/MCP-overview.md and specs/architecture.md for the full protocol
surface planned for M1 (subscribe/list_changed notifications, etc.).
"""
from __future__ import annotations

import json
from typing import Any, Callable

from .catalog import AssetCatalog

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "mcp-catalog-scaffold"
SERVER_VERSION = "0.1.0"

_RESOURCE_SCHEME = "catalog://"

# JSON-RPC / MCP error codes.
_PARSE_ERROR = -32700
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_RESOURCE_NOT_FOUND = -32002


def _resource_uri(asset_id: str) -> str:
    return f"{_RESOURCE_SCHEME}{asset_id}"


def _asset_id_from_uri(uri: str) -> str:
    if not uri.startswith(_RESOURCE_SCHEME):
        raise ValueError(f"Unsupported resource URI scheme: {uri}")
    return uri[len(_RESOURCE_SCHEME) :]


def _mime_type_for(kind: str) -> str:
    return "text/markdown" if kind in {"skill", "instruction", "agent"} else "text/plain"


def _resource_descriptor(asset) -> dict[str, Any]:  # asset: catalog.Asset
    return {
        "uri": _resource_uri(asset.id),
        "name": asset.name,
        "description": asset.description,
        "mimeType": _mime_type_for(asset.kind),
    }


def _error(id_: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def _result(id_: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


# --- Tools (catalog-backed only: no filesystem writes, no model calls) ---

_TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "search_assets": {
        "name": "search_assets",
        "description": (
            "Search the modelless catalog for distributable assets (agent, skill, "
            "prompt, instruction, plugin) by free-text query and/or kind. Returns "
            "summaries only (id, kind, name, version, description) — use "
            "resources/read for an ephemeral load of the full body, or install_asset "
            "for a hard-install descriptor."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text search across id, name, description."},
                "kind": {"type": "string", "description": "Optional filter: agent | skill | prompt | instruction | plugin."},
            },
            "additionalProperties": False,
        },
    },
    "install_asset": {
        "name": "install_asset",
        "description": (
            "Return the anchored install descriptor for a catalog asset (hard "
            "install). The returned `content` is anchored with source/"
            "source_version/source_digest for later drift detection. This tool "
            "performs NO filesystem write: the calling client is responsible for "
            "persisting `content` at `target_path` on its own local filesystem."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string", "description": "Catalog asset id, e.g. 'mermaid-flow'."},
            },
            "required": ["asset_id"],
            "additionalProperties": False,
        },
    },
}


def _tool_search_assets(arguments: dict[str, Any], catalog: AssetCatalog) -> Any:
    query = arguments.get("query")
    kind = arguments.get("kind")
    assets = catalog.search(query, kind=kind) if query else catalog.list(kind=kind)
    return [a.summary() for a in assets]


def _tool_install_asset(arguments: dict[str, Any], catalog: AssetCatalog) -> Any:
    asset_id = arguments.get("asset_id")
    if not asset_id:
        raise ValueError("Missing required argument: asset_id")
    return catalog.get(asset_id).install_descriptor()


_TOOL_HANDLERS: dict[str, Callable[[dict[str, Any], AssetCatalog], Any]] = {
    "search_assets": _tool_search_assets,
    "install_asset": _tool_install_asset,
}


def handle_jsonrpc(payload: dict[str, Any], catalog: AssetCatalog) -> dict[str, Any] | None:
    """Dispatch a single JSON-RPC request/notification.

    Returns ``None`` for notifications (no `id`), which callers must translate to an
    empty HTTP response (e.g. 204), per JSON-RPC 2.0 semantics.
    """
    method = payload.get("method")
    id_ = payload.get("id")
    params = payload.get("params") or {}
    is_notification = "id" not in payload

    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "capabilities": {"resources": {}, "prompts": {}, "tools": {}},
        }
        return _result(id_, result)

    if method == "notifications/initialized":
        return None

    if method == "ping":
        return _result(id_, {})

    if method == "resources/list":
        resources = [_resource_descriptor(a) for a in catalog.list()]
        return _result(id_, {"resources": resources})

    if method == "resources/read":
        uri = params.get("uri")
        if not uri:
            if is_notification:
                return None
            return _error(id_, _INVALID_PARAMS, "Missing required param: uri")
        try:
            asset = catalog.get(_asset_id_from_uri(uri))
        except (KeyError, ValueError) as exc:
            if is_notification:
                return None
            return _error(id_, _RESOURCE_NOT_FOUND, str(exc))
        contents = [
            {
                "uri": uri,
                "mimeType": _mime_type_for(asset.kind),
                # Ephemeral load: raw catalog body, NOT anchored with
                # source/source_version/source_digest (that anchoring only happens
                # on hard install, see catalog.Asset.install_descriptor()).
                "text": asset.body,
            }
        ]
        return _result(id_, {"contents": contents})

    if method == "prompts/list":
        return _result(id_, {"prompts": []})

    if method == "prompts/get":
        if is_notification:
            return None
        return _error(id_, _RESOURCE_NOT_FOUND, "No prompts are registered in this MVP scaffold")

    if method == "tools/list":
        return _result(id_, {"tools": list(_TOOL_DEFINITIONS.values())})

    if method == "tools/call":
        name = params.get("name")
        handler = _TOOL_HANDLERS.get(name)
        if handler is None:
            if is_notification:
                return None
            return _error(id_, _INVALID_PARAMS, f"Unknown tool: {name}")
        arguments = params.get("arguments") or {}
        try:
            data = handler(arguments, catalog)
        except (KeyError, ValueError) as exc:
            # Execution-level error: surfaced as a tool result (isError), not a
            # JSON-RPC error, so the calling model can see and react to it.
            if is_notification:
                return None
            return _result(id_, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
        if is_notification:
            return None
        return _result(
            id_,
            {"content": [{"type": "text", "text": json.dumps(data, indent=2)}], "isError": False},
        )

    if is_notification:
        return None
    return _error(id_, _METHOD_NOT_FOUND, f"Unknown method: {method}")
