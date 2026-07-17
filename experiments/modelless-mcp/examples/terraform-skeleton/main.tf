# Terraform skeleton for the MCP server (Azure Container Apps topology).
#
# THIS IS A TEMPLATE. Do not `terraform apply` against a real subscription without
# review by whoever owns the Azure landing zone. Placeholders are marked <...>.

terraform {
  required_version = ">= 1.6.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.110"
    }
  }
  # backend "azurerm" { ... }   # configure remote state per corporate policy
}

provider "azurerm" {
  features {}
  # subscription_id / tenant_id supplied via env or CLI login
}

variable "location" {
  type    = string
  default = "westeurope"
}

variable "prefix" {
  type    = string
  default = "mcp-mvp"
}

resource "azurerm_resource_group" "rg" {
  name     = "rg-${var.prefix}"
  location = var.location
}

resource "azurerm_container_registry" "acr" {
  name                = replace("${var.prefix}acr", "-", "")
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = "Basic"
  admin_enabled       = false
}

resource "azurerm_key_vault" "kv" {
  name                = "${var.prefix}-kv"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  tenant_id           = "<AAD_TENANT_ID>"
  sku_name            = "standard"
}

resource "azurerm_log_analytics_workspace" "law" {
  name                = "${var.prefix}-law"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = "PerGB2018"
  retention_in_days   = 90
}

resource "azurerm_application_insights" "ai" {
  name                = "${var.prefix}-ai"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  workspace_id        = azurerm_log_analytics_workspace.law.id
  application_type    = "web"
}

resource "azurerm_container_app_environment" "cae" {
  name                       = "${var.prefix}-env"
  resource_group_name        = azurerm_resource_group.rg.name
  location                   = azurerm_resource_group.rg.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.law.id
}

resource "azurerm_container_app" "mcp" {
  name                         = "${var.prefix}-server"
  resource_group_name          = azurerm_resource_group.rg.name
  container_app_environment_id = azurerm_container_app_environment.cae.id
  revision_mode                = "Single"

  identity {
    type = "SystemAssigned"
  }

  ingress {
    external_enabled = true
    target_port      = 8080
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    container {
      name   = "mcp-server"
      image  = "${azurerm_container_registry.acr.login_server}/mcp-server:0.1.0"
      cpu    = 0.5
      memory = "1Gi"
      # Do NOT put secrets here; reference Key Vault via secret refs + Managed Identity.
    }
    min_replicas = 0
    max_replicas = 5
  }
}

# --- Managed data services (uncomment and size per policy) ---
# resource "azurerm_postgresql_flexible_server" "pg" { ... }
# resource "azurerm_redis_cache" "redis" { ... }

output "acr_login_server" {
  value = azurerm_container_registry.acr.login_server
}

output "container_app_fqdn" {
  value = azurerm_container_app.mcp.ingress[0].fqdn
}
