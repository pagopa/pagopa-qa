"""FastAPI application for the MCP catalog control plane (MVP scaffold, modelless).

This exposes a subset of the REST control-plane API described in ../specs/openapi.yml:
health, asset catalog (search / list / manifest), the **install descriptor** for the
hard-install flow, and tenant overrides. The catalog **distributes** assets and
**executes nothing**: it hosts NO model, calls NO model provider, and runs NO
skills. All reasoning and skill execution happen in the client's LOCAL model after
a load or install. The MCP JSON-RPC protocol surface (`POST /mcp`, ephemeral load +
tools) is implemented in `app/mcp_protocol.py` and wired below — see
docs/learn/MCP-overview.md section 5 for the transport.

Assets are loaded at startup from the `manifests/` directory (one `*.yaml` file per
asset — see manifests/manifests.md for the field spec per kind: skill, agent,
prompt, policy). There is intentionally **no runtime write API**: new assets are
added by committing a manifest (`manifests/<kind-plural>/<kind>.<id>.yaml`) and,
if using `body_file`, its content (`assets/<kind-plural>/<kind>.<id>.md`) to the
repo — see the
`add-catalog-asset` skill (`.github/skills/add-catalog-asset/SKILL.md`) for the
authoring procedure. Because the Dockerfile does `COPY manifests ./manifests` and
`COPY assets ./assets` + `COPY app ./app`, the next image build/rebuild picks up
any new file automatically;
no server-side registration endpoint is needed.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from .auth import Principal, get_principal, require_role
from .catalog import AssetCatalog
from .mcp_protocol import handle_jsonrpc
from .tenants import TenantConfig

APP_VERSION = "0.1.0"
_STARTED = time.time()

# manifests/ lives one level up from app/, at the scaffold root (sibling of app/).
MANIFESTS_DIR = Path(__file__).parent.parent / "manifests"

app = FastAPI(title="MCP Catalog — Control Plane (modelless)", version=APP_VERSION)

# --- Wiring (MVP: in-memory, seeded from manifests/**/*.yaml at startup) ---
catalog = AssetCatalog()
tenants = TenantConfig()
catalog.load_dir(MANIFESTS_DIR)


# --- Schemas ---
class OverridesBody(BaseModel):
    asset_params: dict | None = None
    quotas: dict | None = None


# --- Endpoints ---
@app.get("/v1/health")
def health() -> dict:
    return {"status": "ok", "version": APP_VERSION, "uptime_s": int(time.time() - _STARTED)}


@app.get("/v1/assets")
def list_assets(
    kind: str | None = None,
    q: str | None = None,
    principal: Principal = Depends(get_principal),
) -> list[dict]:
    assets = catalog.search(q, kind=kind) if q is not None else catalog.list(kind=kind)
    return [a.summary() for a in assets]


@app.get("/v1/assets/{asset_id}")
def get_asset_manifest(
    asset_id: str,
    principal: Principal = Depends(get_principal),
) -> dict:
    try:
        return catalog.get(asset_id).manifest()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/v1/assets/{asset_id}/install")
def get_install_descriptor(
    asset_id: str,
    principal: Principal = Depends(get_principal),
) -> dict:
    """Return the descriptor the client uses to materialize the asset as a local
    file (with source_version + source_digest anchored for drift detection). The
    catalog executes nothing.
    """
    try:
        return catalog.get(asset_id).install_descriptor()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/v1/tenants/{tenant_id}/overrides")
def get_overrides(
    tenant_id: str,
    principal: Principal = Depends(get_principal),
) -> dict:
    return {"tenant_id": tenant_id, **tenants.get_overrides(tenant_id)}


@app.put("/v1/tenants/{tenant_id}/overrides")
def put_overrides(
    tenant_id: str,
    body: OverridesBody,
    principal: Principal = Depends(get_principal),
) -> dict:
    require_role(principal, "admin")
    tenants.set_overrides(tenant_id, body.model_dump(exclude_none=True))
    return {"tenant_id": tenant_id, **tenants.get_overrides(tenant_id)}


@app.post("/mcp")
async def mcp_endpoint(
    request: Request,
    principal: Principal = Depends(get_principal),
) -> Response:
    """MCP JSON-RPC endpoint (Streamable HTTP), the **ephemeral load** surface.

    Register this URL as an MCP server in VS Code (`.vscode/mcp.json`, type
    "http"). It executes nothing: `resources/read` only returns the raw catalog
    body for the client's local model to use in the current session. See
    app/mcp_protocol.py for the supported methods.
    """
    payload = await request.json()
    result = handle_jsonrpc(payload, catalog)
    if result is None:
        # JSON-RPC notification (no "id"): no response body per spec.
        return Response(status_code=204)
    return Response(content=json.dumps(result), media_type="application/json")
