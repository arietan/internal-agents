resource "azurerm_service_plan" "agents" {
  name                = "${var.name_prefix}-${var.environment}-plan"
  resource_group_name = var.resource_group_name
  location            = var.location
  os_type             = "Linux"
  sku_name            = "EP1"
  tags                = { Component = "compute" }
}

resource "azurerm_storage_account" "functions" {
  name                     = "${var.name_prefix}${var.environment}fn"
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_linux_function_app" "agents" {
  name                = "${var.name_prefix}-${var.environment}-func"
  resource_group_name = var.resource_group_name
  location            = var.location
  service_plan_id     = azurerm_service_plan.agents.id

  storage_account_name       = azurerm_storage_account.functions.name
  storage_account_access_key = azurerm_storage_account.functions.primary_access_key

  site_config {
    application_stack {
      python_version = "3.12"
    }
    application_insights_key               = var.appinsights_key
    application_insights_connection_string = var.appinsights_conn
  }

  app_settings = {
    CLOUD_PROVIDER               = "azure"
    COSMOS_ENDPOINT              = ""
    KEY_VAULT_URL                = var.keyvault_uri
    CONTENT_SAFETY_USE_IDENTITY  = "true"
    AZURE_OPENAI_USE_ENTRA       = "true"
    AzureWebJobsStorage          = azurerm_storage_account.functions.primary_connection_string
    FUNCTIONS_WORKER_RUNTIME     = "python"
    WEBSITE_RUN_FROM_PACKAGE     = "1"
    APPLICATIONINSIGHTS_CONNECTION_STRING = var.appinsights_conn
  }

  identity {
    type = "SystemAssigned"
  }

  tags = { Component = "compute" }
}

variable "environment" { type = string }
variable "name_prefix" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "storage_account_id" { type = string }
variable "cosmos_connection" {
  type      = string
  sensitive = true
}
variable "keyvault_uri" { type = string }
variable "appinsights_key" { type = string }
variable "appinsights_conn" { type = string }

output "function_app_id" { value = azurerm_linux_function_app.agents.id }
output "function_app_name" { value = azurerm_linux_function_app.agents.name }
