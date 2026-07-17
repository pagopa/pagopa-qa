# Terraform skeleton — README

Template Terraform for the **Azure Container Apps** topology of the MCP server.

## Files

- `main.tf` — resource group, ACR, Key Vault, Log Analytics, App Insights,
  Container App environment + app. Managed Postgres/Redis are stubbed as comments.

## Usage (review before running)

```bash
terraform init
terraform plan  -var "prefix=mcp-mvp" -var "location=westeurope"
terraform apply -var "prefix=mcp-mvp" -var "location=westeurope"
```

## Important

- Replace every `<...>` placeholder (AAD tenant id, backend config).
- Configure a **remote state backend** (`backend "azurerm"`) per corporate policy.
- Never store secrets in `.tf` files; use Key Vault + Managed Identity references.
- Have the Azure landing-zone owner review naming, regions, and networking.
