"""Asset catalog for the MCP catalog control plane (MVP scaffold, modelless).

This is a **catalog**, not an execution engine. It stores versioned AI assets
(agent / skill / prompt / policy / plugin), each with a content *body* served to the
client, and it can build an **install descriptor** for the `hard install` flow. It
runs nothing: there is no entrypoint, no isolation, and no `run`. Execution and
reasoning happen in the client's LOCAL model after a load or install.

See ../manifests/manifests.md for the manifest field spec (per kind: skill, agent,
prompt, policy) and ../../specs/openapi.yml for the REST control-plane contract.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_ASSETS_DIR = Path(__file__).parent.parent / "assets"


def _digest(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass
class Asset:
    """A versioned, distributable asset. The catalog serves it; it never runs it."""

    id: str
    kind: str
    name: str
    version: str
    description: str
    visibility: str
    body: str
    install_target: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def digest(self) -> str:
        return _digest(self.body)

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "version": self.version,
            "visibility": self.visibility,
            "description": self.description,
        }

    def manifest(self) -> dict[str, Any]:
        return {
            **self.summary(),
            "digest": self.digest,
            "body_ref": self.metadata.get("source", self.install_target),
            "install": {
                "target_path": self.install_target,
                "files": [],
                "frontmatter_anchor": True,
            },
        }

    def install_descriptor(self) -> dict[str, Any]:
        """Everything the client needs to materialize the asset as a local file
        and later detect drift against the catalog (source_version + source_digest).
        """
        anchored = _anchor_frontmatter(
            self.body,
            source="mcp-catalog",
            source_version=self.version,
            source_digest=self.digest,
        )
        return {
            "id": self.id,
            "kind": self.kind,
            "source_version": self.version,
            "source_digest": self.digest,
            "target_path": self.install_target,
            "content": anchored,
            "files": [],
        }


def _anchor_frontmatter(body: str, *, source: str, source_version: str, source_digest: str) -> str:
    """Inject provenance/version anchors so the installed copy can be drift-checked.

    If the body already starts with a YAML frontmatter block (``---``), the anchors
    are merged into it; otherwise a new frontmatter block is prepended.
    """
    anchors = {
        "source": source,
        "source_version": source_version,
        "source_digest": source_digest,
    }
    if body.startswith("---\n"):
        end = body.find("\n---", 4)
        if end != -1:
            fm_text = body[4:end]
            rest = body[end + 4 :]
            data = yaml.safe_load(fm_text) or {}
            data.update(anchors)
            new_fm = yaml.safe_dump(data, sort_keys=False).strip()
            return f"---\n{new_fm}\n---{rest}"
    new_fm = yaml.safe_dump(anchors, sort_keys=False).strip()
    return f"---\n{new_fm}\n---\n\n{body}"


class AssetCatalog:
    """In-memory catalog for the MVP. Production stores assets in Postgres/blob."""

    def __init__(self) -> None:
        self._assets: dict[str, Asset] = {}

    def load_dir(self, manifests_dir: str | Path) -> None:
        """Register every ``*.yaml`` manifest found under ``manifests_dir``.

        Discovery is recursive so manifests can be organized by kind
        (``manifests/agents/``, ``manifests/skills/``, ...). Template files under
        ``manifests/_templates/`` are always skipped.
        """
        root = Path(manifests_dir)
        for path in sorted(root.rglob("*.yaml")):
            if "_templates" in path.parts:
                continue
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.register_dict(data)

    def register_dict(self, data: dict[str, Any]) -> None:
        """Register one asset manifest (as parsed from YAML/JSON).

        Accepts the real manifest schema (see ../manifests/manifests.md):
        - ``install.target_path`` (nested) falls back to a flat ``install_target``
          key for convenience (unit tests, programmatic registration).
        - Body resolution priority: inline ``body`` -> (for ``kind: prompt``)
                    inline ``template`` -> ``body_file`` (path relative to ``assets/``).
        """
        required = ["id", "kind", "name", "version"]
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(f"Asset manifest missing fields: {missing}")

        kind = data["kind"]

        install_target = data.get("install_target")
        if install_target is None:
            install_target = (data.get("install") or {}).get("target_path")
        if not install_target:
            raise ValueError(
                f"Asset '{data['id']}' has no install_target (or install.target_path)"
            )

        body = data.get("body")
        if body is None and kind == "prompt":
            body = data.get("template")
        if body is None:
            body_file = data.get("body_file")
            if not body_file:
                raise ValueError(f"Asset '{data['id']}' has no body, body_file, or template")
            body = (_ASSETS_DIR / body_file).read_text(encoding="utf-8")

        asset = Asset(
            id=data["id"],
            kind=kind,
            name=data["name"],
            version=data["version"],
            description=data.get("description", ""),
            visibility=data.get("visibility", "private"),
            body=body,
            install_target=install_target,
            metadata=data.get("metadata", {}),
        )
        self._assets[asset.id] = asset

    def list(self, kind: str | None = None) -> list[Asset]:
        assets = self._assets.values()
        if kind is not None:
            assets = [a for a in assets if a.kind == kind]
        return list(assets)

    def search(self, query: str, kind: str | None = None) -> list[Asset]:
        q = query.lower().strip()
        results = []
        for asset in self.list(kind):
            haystack = f"{asset.id} {asset.name} {asset.description}".lower()
            if not q or q in haystack:
                results.append(asset)
        return results

    def get(self, asset_id: str) -> Asset:
        if asset_id not in self._assets:
            raise KeyError(f"Asset not found: {asset_id}")
        return self._assets[asset_id]
