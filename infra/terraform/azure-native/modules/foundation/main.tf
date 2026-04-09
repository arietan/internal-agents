resource "azurerm_resource_group" "agents" {
  name     = "${var.name_prefix}-${var.environment}-rg"
  location = var.location
  tags     = { Project = "internal-agents", Environment = var.environment, ManagedBy = "terraform" }
}

resource "azurerm_cosmosdb_account" "audit" {
  name                = "${var.name_prefix}-${var.environment}-cosmos"
  location            = var.location
  resource_group_name = azurerm_resource_group.agents.name
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"

  capabilities { name = "EnableServerless" }

  consistency_policy { consistency_level = "Session" }

  geo_location {
    location          = var.location
    failover_priority = 0
  }

  tags = { Component = "audit" }
}

resource "azurerm_cosmosdb_sql_database" "agents" {
  name                = "internal-agents"
  resource_group_name = azurerm_resource_group.agents.name
  account_name        = azurerm_cosmosdb_account.audit.name
}

resource "azurerm_cosmosdb_sql_container" "audit_trail" {
  name                = "audit-trail"
  resource_group_name = azurerm_resource_group.agents.name
  account_name        = azurerm_cosmosdb_account.audit.name
  database_name       = azurerm_cosmosdb_sql_database.agents.name
  partition_key_path  = "/partitionKey"

  indexing_policy {
    indexing_mode = "consistent"
    included_path { path = "/agent_name/?" }
    included_path { path = "/timestamp/?" }
    included_path { path = "/target_repo/?" }
  }
}

resource "azurerm_storage_account" "config" {
  name                     = "${var.name_prefix}${var.environment}cfg"
  resource_group_name      = azurerm_resource_group.agents.name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"

  blob_properties {
    versioning_enabled = true
  }

  tags = { Component = "config" }
}

resource "azurerm_key_vault" "agents" {
  name                = "${var.name_prefix}-${var.environment}-kv"
  location            = var.location
  resource_group_name = azurerm_resource_group.agents.name
  sku_name            = "standard"
  tenant_id           = data.azurerm_client_config.current.tenant_id

  purge_protection_enabled   = true
  soft_delete_retention_days = 90

  tags = { Component = "secrets" }
}

data "azurerm_client_config" "current" {}

variable "environment" { type = string }
variable "name_prefix" { type = string }
variable "location" { type = string }

output "resource_group_name" { value = azurerm_resource_group.agents.name }
output "cosmos_connection_string" {
  value     = azurerm_cosmosdb_account.audit.primary_sql_connection_string
  sensitive = true
}
output "storage_account_id" { value = azurerm_storage_account.config.id }
output "keyvault_uri" { value = azurerm_key_vault.agents.vault_uri }
