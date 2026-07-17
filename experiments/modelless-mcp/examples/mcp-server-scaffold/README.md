# MCP Catalog — MVP Scaffold

Minimal, runnable FastAPI scaffold for the QA MCP **catalog** control plane
(modelless). It ships a sample distributed asset (`mermaid-flow`), catalog
search/manifest endpoints, an **install descriptor** endpoint for the hard-install
flow, tenant override resolution, and a dev auth stub. The catalog **distributes**
assets and **executes nothing**: it hosts and calls **no model** and runs **no
skills**. Reasoning and skill execution happen in the client's local model.

> This is a **starting point** to copy into the future dedicated `mcp-catalog`
> repository. See `../../NEXT_STEPS.md`.

## Layout

```text
mcp-server-scaffold/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI control-plane endpoints (catalog + install)
│   ├── auth.py           # Azure AD stub (replace with real JWKS validation)
│   ├── catalog.py        # Asset catalog: list/search/manifest/install (no execution)
│   ├── tenants.py        # Tenant override resolution
│   └── assets/
│       └── skill.mermaid-flow.md   # sample distributed asset (content, not code)
├── tests/                # unit + contract tests
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
└── pytest.ini
```

## Run locally

```powershell
cd mcp_blueprint/modelless-mcp/examples/mcp-server-scaffold
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
$env:MCP_AUTH_DISABLED = "1"
uvicorn app.main:app --reload --port 8080
```

Then open http://127.0.0.1:8080/docs (interactive OpenAPI UI).

## Try it

```powershell
# Health (public)
curl http://127.0.0.1:8080/v1/health

# Browse / search the catalog
curl http://127.0.0.1:8080/v1/assets
curl "http://127.0.0.1:8080/v1/assets?q=mermaid&kind=skill"

# Read an asset manifest (version + digest + install target)
curl http://127.0.0.1:8080/v1/assets/mermaid-flow

# Get the install descriptor (hard install): file content with
# source_version/source_digest anchored for drift detection
curl http://127.0.0.1:8080/v1/assets/mermaid-flow/install
```

## Connect it to VS Code (ephemeral load, MCP JSON-RPC)

The server also exposes a minimal **MCP JSON-RPC endpoint** at `POST /mcp`
(Streamable HTTP). This is the **ephemeral load** surface: `resources/read` returns
the raw asset body for the current chat session, with **no** install/version
anchoring (that only happens on hard install, via `/v1/assets/{id}/install`).

Register it in `.vscode/mcp.json` (workspace) or your user MCP settings:

```json
{
  "servers": {
    "mcp-catalog-local": {
      "type": "http",
      "url": "http://127.0.0.1:8080/mcp"
    }
  }
}
```

Then, from the MCP panel in VS Code, start/connect to `mcp-catalog-local` and use
"List Resources" / "Read Resource" on `catalog://mermaid-flow`. Supported methods:
`initialize`, `notifications/initialized`, `ping`, `resources/list`,
`resources/read`, `prompts/list`, `prompts/get` (empty for this MVP),
`tools/list`, `tools/call`. See `app/mcp_protocol.py` for the implementation and
`../../docs/learn/MCP-overview.md` for the full protocol surface planned for M1.

### Tools (`tools/list`, `tools/call`)

Two catalog-backed tools are exposed so a chat agent can drive both flows without
manual REST calls — ask for them in natural language, e.g.:

- **Ephemeral discovery**: "Search the MCP catalog for assets about mermaid" ->
  invokes `search_assets` (`query`, optional `kind`), returns summaries only.
- **Hard install**: "Install the mermaid-flow asset from the MCP catalog" ->
  invokes `install_asset` (`asset_id`), returns the anchored descriptor
  (`target_path`, `content` with `source`/`source_version`/`source_digest`
  anchors, `source_digest`). The tool performs **no filesystem write** — the
  calling client (your local agent) must write `content` to `target_path` itself.

Both tools only read the in-memory catalog; they never write files or call a model.

> No new container is needed to try this: it's the same FastAPI app on the same
> port. If you changed code after building the image, just rebuild and restart the
> existing service (`docker compose up --build`), you don't need to add another one.

## Test

```powershell
$env:MCP_AUTH_DISABLED = "1"
pytest --cov=app --cov-report=term-missing
```

## No models, no execution

This scaffold intentionally has **no model router, no adapters, no provider SDKs,
and no execution engine**. The catalog only distributes versioned asset content and
builds install descriptors. Any reasoning and skill execution are performed by the
consumer's local model (their Copilot seat), outside this server.

## Notes

- Auth here is a **dev stub**. Replace `app/auth.py::_decode` with real Azure AD
  JWT validation (JWKS signature + audience + expiry) before any shared deployment.
- The MCP JSON-RPC endpoint (`/mcp`) covers `resources/*`, `prompts/list` (empty),
  and `tools/*` (`search_assets`, `install_asset`) for the MVP — no
  `resources/subscribe`/`list_changed` notifications yet. See
  `../../docs/learn/MCP-overview.md` §5 and `../../plan/implementation_plan.md` M1
  for what's still planned.
