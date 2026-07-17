"""Unit tests for the AssetCatalog (distribution only, no execution)."""
import hashlib

from app.catalog import Asset, AssetCatalog


def _make_asset(body: str = "# Hello\n") -> Asset:
    return Asset(
        id="sample",
        kind="skill",
        name="Sample",
        version="2.1.0",
        description="A sample distributed asset",
        visibility="public",
        body=body,
        install_target=".github/skills/sample/SKILL.md",
    )


def test_digest_is_sha256_of_body():
    asset = _make_asset("content")
    expected = "sha256:" + hashlib.sha256(b"content").hexdigest()
    assert asset.digest == expected


def test_manifest_exposes_install_and_digest():
    manifest = _make_asset().manifest()
    assert manifest["id"] == "sample"
    assert manifest["digest"].startswith("sha256:")
    assert manifest["install"]["target_path"] == ".github/skills/sample/SKILL.md"


def test_install_descriptor_anchors_into_existing_frontmatter():
    body = "---\nname: sample\n---\n\n# Body\n"
    asset = _make_asset(body)
    desc = asset.install_descriptor()
    assert desc["source_version"] == "2.1.0"
    assert "name: sample" in desc["content"]
    assert "source: mcp-catalog" in desc["content"]
    assert "source_version: 2.1.0" in desc["content"]
    assert desc["source_digest"] in desc["content"]
    # No duplicate frontmatter fences introduced.
    assert desc["content"].count("---") == 2


def test_install_descriptor_prepends_frontmatter_when_absent():
    asset = _make_asset("# Just body, no frontmatter\n")
    content = asset.install_descriptor()["content"]
    assert content.startswith("---\n")
    assert "source: mcp-catalog" in content


def test_search_and_list_filtering():
    catalog = AssetCatalog()
    catalog.register_dict(
        {
            "id": "a1",
            "kind": "skill",
            "name": "Alpha",
            "version": "1.0.0",
            "install_target": ".github/skills/a1/SKILL.md",
            "body": "alpha body",
        }
    )
    catalog.register_dict(
        {
            "id": "p1",
            "kind": "prompt",
            "name": "Prompt One",
            "version": "1.0.0",
            "install_target": ".github/prompts/p1.prompt.md",
            "body": "prompt body",
        }
    )
    assert {a.id for a in catalog.list()} == {"a1", "p1"}
    assert {a.id for a in catalog.list(kind="skill")} == {"a1"}
    assert {a.id for a in catalog.search("alpha")} == {"a1"}
    assert catalog.search("nothing") == []


def test_missing_body_raises():
    catalog = AssetCatalog()
    try:
        catalog.register_dict(
            {
                "id": "x",
                "kind": "skill",
                "name": "X",
                "version": "1.0.0",
                "install_target": ".github/skills/x/SKILL.md",
            }
        )
    except ValueError as exc:
        assert "body" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for missing body")


def test_nested_install_target_path_is_accepted():
    """Real manifests use install.target_path (not the flat install_target)."""
    catalog = AssetCatalog()
    catalog.register_dict(
        {
            "id": "nested-install",
            "kind": "skill",
            "name": "Nested Install",
            "version": "1.0.0",
            "body": "content",
            "install": {"target_path": ".github/skills/nested-install/SKILL.md"},
        }
    )
    asset = catalog.get("nested-install")
    assert asset.install_target == ".github/skills/nested-install/SKILL.md"


def test_missing_install_target_raises():
    catalog = AssetCatalog()
    try:
        catalog.register_dict(
            {
                "id": "no-install",
                "kind": "skill",
                "name": "No Install",
                "version": "1.0.0",
                "body": "content",
            }
        )
    except ValueError as exc:
        assert "install_target" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for missing install target")


def test_prompt_falls_back_to_template_as_body():
    """Prompt manifests carry their content in `template`, not `body`/`body_file`."""
    catalog = AssetCatalog()
    catalog.register_dict(
        {
            "id": "sample-prompt",
            "kind": "prompt",
            "name": "Sample Prompt",
            "version": "1.0.0",
            "install": {"target_path": ".github/prompts/sample-prompt.prompt.md"},
            "template": "Do the thing: ${objective}",
        }
    )
    asset = catalog.get("sample-prompt")
    assert asset.body == "Do the thing: ${objective}"


def test_load_dir_is_recursive_and_skips_templates(tmp_path):
    """Load manifests from kind subfolders while ignoring _templates."""
    manifests_dir = tmp_path / "manifests"
    (manifests_dir / "skills").mkdir(parents=True)
    (manifests_dir / "_templates").mkdir(parents=True)

    (manifests_dir / "skills" / "skill.recursive.yaml").write_text(
        "id: recursive\n"
        "kind: skill\n"
        "name: Recursive Skill\n"
        "version: 1.0.0\n"
        "install:\n"
        "  target_path: .github/skills/recursive/SKILL.md\n"
        "body: recursive body\n",
        encoding="utf-8",
    )
    (manifests_dir / "_templates" / "skill.yaml").write_text(
        "kind: skill\n",
        encoding="utf-8",
    )

    catalog = AssetCatalog()
    catalog.load_dir(manifests_dir)

    assert {a.id for a in catalog.list()} == {"recursive"}
