# Asset Manifests — Specification

> Language: English (technical specification). Sample files live alongside this
> document (`skills/skill.mermaid-flow.yaml`, `agents/agent.qa-orchestrator.yaml`,
> `prompts/prompt.qa.yaml`, `policies/policy.gherkin.yaml`). Starter templates for each
> kind live in [_templates/](_templates/) — copy one, fill in the placeholders,
> drop it under `<kind-plural>/` as `<kind>.<id>.yaml`.
>
> **These manifests are the real source of truth**: `AssetCatalog.load_dir()` (see
> `../app/catalog.py`) registers every `*.yaml` file in this folder recursively at
> server startup (`../app/main.py`), excluding `_templates/`. There is no runtime
> write API — new assets are added by authoring a manifest (and, if using
> `body_file`, its content under `../assets/<kind-plural>/`) and committing it to the
> repo; the next image build/rebuild picks it up automatically (`COPY manifests`/
> `COPY assets` + `COPY app` in the `Dockerfile`). See
> the `add-catalog-asset` skill (`.github/skills/add-catalog-asset/SKILL.md`) for
> the authoring procedure, including deterministic `kind`/`id`/`description`
> inference from a source `.md` file.

## 1. Purpose

Every AI asset (agent, skill, prompt, policy, plugin) exposed by the MCP **catalog** is
described by a **manifest**. Manifests make assets:

- **discoverable** (catalog listing),
- **validatable** (typed inputs/outputs),
- **governable** (permissions, provenance & signing),
- **versionable** (immutable semver + digest), and
- **customizable** (declared `custom_params` overridable per tenant/request).

Manifests are authored in **YAML** (human-friendly) and validated against JSON
Schema at registration time.

> Note: this is the **modelless catalog** variant. The server **distributes** assets
> and **does not execute** them. No manifest references a model, a model provider, a
> `model:call` permission, or any server-side execution runtime (no `entrypoint`,
> `isolation`, or `resource_limits`). Reasoning and skill execution stay in the
> client's local model; the manifest describes **what is distributed** and **how it is
> installed**, not how the server runs it.

## 2. Common fields (all asset kinds)

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes | Stable unique identifier (kebab-case) |
| `kind` | enum | yes | `agent` \| `skill` \| `prompt` \| `policy` \| `plugin` |
| `name` | string | yes | Human-readable name |
| `version` | semver | yes | Immutable version, e.g. `1.0.0` |
| `digest` | string | yes | Content digest, e.g. `sha256:…`, anchored on install |
| `description` | string | yes | What it does / when to use |
| `visibility` | enum | yes | `public` \| `private` |
| `owner` | string | yes | Team or contact |
| `provenance` | object | no | Publisher, source commit, signature ref |
| `custom_params` | ParamSpec[] | no | Tenant/request-overridable parameters |
| `metadata` | object | no | Free-form tags/labels |

### ParamSpec

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Parameter name |
| `type` | enum | yes | `string`\|`integer`\|`number`\|`boolean`\|`object`\|`array` |
| `required` | boolean | no | Default `false` |
| `description` | string | no | Human description |
| `default` | any | no | Default value |
| `enum` | any[] | no | Allowed values |

### InstallSpec

Describes how a client **materializes** the asset on `hard install` (see the three
consumption modes in [MCP-overview.md](../docs/learn/MCP-overview.md)).

| Field | Type | Default | Description |
|---|---|---|---|
| `target_path` | string | (by kind) | Local destination, e.g. `.github/skills/<id>/SKILL.md` |
| `files` | string[] | `[]` | Additional files/attachments to install |
| `frontmatter_anchor` | boolean | `true` | Write `source`, `source_version`, `source_digest` into the installed file for drift detection |

## 3. Skill manifest

A skill is a **distributed asset**: the catalog delivers it (load or install) and the
**client's local model executes it**. The manifest declares the skill's interface and
how it is installed — **not** how the server runs it (the server runs nothing):

| Field | Type | Required | Description |
|---|---|---|---|
| `inputs` | ParamSpec[] | no | Declared inputs the local model expects |
| `outputs` | ParamSpec[] | no | Declared outputs / output contract |
| `body` / `body_file` | string | one required | Inline content, or a path (for example `skills/skill.my-skill.md`) resolved under `assets/` |
| `install` | InstallSpec | **yes** | How to hard-install the skill locally (`target_path` required) |
| `dependencies` | string[] | no | Documented local prerequisites (e.g. `src/utility`, external CLIs) |

There are **no** `entrypoint`, `isolation`, `resource_limits`, `timeout_s`, or
`network` fields: the server neither executes the skill nor sandboxes it.

Maps from: `.github/skills/<name>/SKILL.md` (frontmatter `name`, `description`,
`applyTo` → metadata; body → the skill content the local model applies).

## 4. Agent manifest

Describes an agent **definition** served as a resource. The server does not run
agents; the client's local model orchestrates them. There is **no `model` field**,
because the model is always the client's local one:

| Field | Type | Required | Description |
|---|---|---|---|
| `tools` | string[] | no | Allowed tool names (allow-list) |
| `subagents` | string[] | no | Agent ids reachable via handoff |
| `handoffs` | Handoff[] | no | Declared transitions |
| `user_invocable` | boolean | no | Whether end-users can call directly |
| `instructions_ref` | string[] | no | Policy assets to inject as context |
| `body` / `body_file` | string | one required | Inline content, or a path resolved under `assets/` |
| `install` | InstallSpec | **yes** | How to hard-install the agent definition locally (`target_path` required) |

### Handoff

| Field | Type | Description |
|---|---|---|
| `label` | string | UI label |
| `agent` | string | Target agent id |
| `prompt` | string | Handoff prompt |
| `auto` | boolean | Invisible (orchestrated) vs visible (button) |

Maps from: `.github/agents/*.agent.md` frontmatter (`tools`, `agents`,
`handoffs`, `user-invocable`). Any `model` field in the source is ignored.

## 5. Prompt manifest

| Field | Type | Required | Description |
|---|---|---|---|
| `arguments` | ParamSpec[] | no | Typed args (from `${input:...}`) |
| `target_agent` | string | no | Agent this prompt drives |
| `template` | string | one required | Template body with placeholders; also serves as the prompt's `body` |
| `fallback_to_context` | boolean | no | Use chat context if no input |
| `install` | InstallSpec | **yes** | How to hard-install the prompt locally (`target_path` required) |

Maps from: `.github/prompts/*.prompt.md` frontmatter + body.

## 6. Policy manifest

> **Policy vs. instruction — same concept, one kind.** `policy` is the catalog's
> single kind for grounding/convention documents; it is the exact counterpart of a
> repo `.github/instructions/*.instructions.md` file. There is intentionally **no**
> separate `instruction` kind — use `policy` for anything that would otherwise be
> an "instruction" file (conventions, style rules, guardrails injected as context,
> never executed).

| Field | Type | Required | Description |
|---|---|---|---|
| `apply_to` | string | no | Glob pattern that scopes the policy |
| `body` / `body_file` | string | one required | Inline content, or a path resolved under `assets/` |
| `injectable` | boolean | no | Whether it can be injected as grounding |
| `install` | InstallSpec | **yes** | How to hard-install the policy locally (`target_path` required) |

Maps from: `.github/instructions/*.instructions.md`.

## 7. Validation rules

- `id` unique within `kind`.
- `version` must be valid semver and **immutable** once registered.
- `digest` must be present and match the served content (verified by the client on install).
- All `inputs`/`outputs`/`custom_params` names unique within the manifest.
- No manifest may declare a model, a provider, a `model:call` permission, or any
  server-side execution field (`entrypoint`, `isolation`, `resource_limits`, `timeout_s`).
- Unknown top-level fields are rejected (strict schema).

## 8. Override semantics

`custom_params` and selected fields (`style`) are overridable. Precedence:

```text
manifest default  <  tenant override  <  request-time parameter
```

Non-overridable fields (e.g. `permissions`, `visibility`, `digest`, `install.target_path`)
are fixed by governance and cannot be changed by tenants. There is no model-related
override.

## 9. Sample files

- Skill: [skills/skill.mermaid-flow.yaml](skills/skill.mermaid-flow.yaml)
- Agent: [agents/agent.qa-orchestrator.yaml](agents/agent.qa-orchestrator.yaml)
- Prompt: [prompts/prompt.qa.yaml](prompts/prompt.qa.yaml)
- Policy: [policies/policy.gherkin.yaml](policies/policy.gherkin.yaml)
- Blank templates (one per kind, not loaded at startup): [_templates/](_templates/)
