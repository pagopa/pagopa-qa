# Azure Deployment Guide

> Language: English (operational guide). Companion learning doc (Italian):
> [security_and_runtime.md](../../docs/learn/security_and_runtime.md).
>
> Audience note: written to be followable even if you are new to Azure. Every
> resource is explained in one line ("what it is / why we need it").

## 1. What we are deploying

A containerized MCP **catalog** (modelless) reachable over HTTPS by other teams,
authenticated with Azure AD, backed by managed data services, with secrets in Key
Vault and telemetry in Application Insights. The catalog **distributes** assets
(load / install / notifications) and **executes nothing**: it hosts **no model**,
calls **no model provider**, and runs **no skills** server-side.

## 2. Two topologies

### 2.1 Recommended: Azure Container Apps (ACA) — simplest to operate

Best for the MVP and most likely fine for a good while. Serverless containers,
built-in ingress, scale-to-zero, easy revisions.

| Azure resource | What it is / why |
|---|---|
| Azure Container Apps | Runs the MCP catalog container; handles HTTPS ingress and autoscale |
| Azure Container Registry (ACR) | Stores the Docker image we build |
| Azure Key Vault | Stores secrets (DB connection); app reads via Managed Identity |
| Azure Database for PostgreSQL (Flexible) | Persistent state: assets, versions, tenants, audit |
| Azure Cache for Redis | Cache for catalog reads and notification/version state |
| Application Insights + Log Analytics | Telemetry, logs, metrics, alerts |
| Managed Identity | App identity to access Key Vault/DB without stored credentials |
| (Optional) API Management | Central gateway: rate limiting, subscription keys, JWT policy |

### 2.2 Enterprise: AKS (Kubernetes) — maximum control

Choose when you need network policies, private networking, and fine-grained scaling
for a high-traffic catalog. Note: there are **no skill workers** to isolate — the
catalog runs nothing; this topology is about scale and network control, not sandboxing.

| Extra vs ACA | Why |
|---|---|
| AKS cluster | Full Kubernetes control, node pools, network policies |
| Helm charts | Declarative, repeatable deployments (skeleton provided) |
| Dedicated node pool | Scale the stateless catalog read/serve tier independently |

## 3. Identity & auth setup (Azure AD / Entra ID)

1. **App registration** for the MCP server (exposes an API scope, e.g.
   `api://mcp-server/.default`).
2. **App registrations or existing groups** for each consuming team (tenant).
3. Map Entra ID **groups → tenant roles** (`user`, `admin`) used by RBAC.
4. Consuming clients obtain tokens via **client credentials** (service-to-service)
   or **on-behalf-of** (user context).

## 4. Networking & security baseline

- HTTPS only; TLS terminated at ingress / API Management.
- `/v1/health` public; everything else requires a valid Bearer token.
- Secrets exclusively in Key Vault, accessed via Managed Identity.
- Catalog egress is minimal (serves stored content; no per-request skill execution).
- Private endpoints for Postgres/Redis where policy requires.

## 5. CI/CD

A GitHub Actions workflow (skeleton in
[../../examples/ci/github-actions-deploy.yml](../../examples/ci/github-actions-deploy.yml))
does: lint + test → build image → push to ACR → deploy to ACA/AKS. Auth to Azure
uses **OIDC federation** (no long-lived cloud credentials in GitHub).

## 6. IaC (Infrastructure as Code)

Skeletons provided (fill placeholders, do not run against real subscriptions
without review):

- Terraform: [../../examples/terraform-skeleton/](../../examples/terraform-skeleton/)
- Helm chart: [../../examples/helm-skeleton/](../../examples/helm-skeleton/)

## 7. Cost awareness (rough, non-binding)

- ACA scales to zero → near-zero when idle.
- No inference cost: the server calls no model (reasoning is on the client's seat).
- Postgres/Redis smallest managed tiers are fine for MVP.

## 8. Step-by-step (ACA, high level)

```bash
# 1. Login and pick subscription
az login
az account set --subscription "<SUBSCRIPTION_ID>"

# 2. Resource group
az group create -n rg-mcp-mvp -l westeurope

# 3. Container registry + build/push
az acr create -g rg-mcp-mvp -n <acrName> --sku Basic
az acr build -r <acrName> -t mcp-server:0.1.0 .

# 4. Key Vault + secrets
az keyvault create -g rg-mcp-mvp -n <kvName> -l westeurope
# az keyvault secret set --vault-name <kvName> -n db-connection --value <...>

# 5. Container App environment + app
az containerapp env create -g rg-mcp-mvp -n mcp-env -l westeurope
az containerapp create -g rg-mcp-mvp -n mcp-server \
  --environment mcp-env \
  --image <acrName>.azurecr.io/mcp-server:0.1.0 \
  --ingress external --target-port 8080 \
  --system-assigned

# 6. Grant the app access to Key Vault (Managed Identity), configure telemetry, etc.
```

> The exact commands depend on corporate policies (naming, regions, private
> networking). Treat this as a template to hand to whoever owns the Azure landing
> zone. See [../../NEXT_STEPS.md](../../NEXT_STEPS.md) for what to request from IT.
