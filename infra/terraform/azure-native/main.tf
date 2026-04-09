terraform {
  required_version = ">= 1.5"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.80"
    }
  }

  backend "azurerm" {
    resource_group_name  = "internal-agents-tfstate"
    storage_account_name = "iagentstfstate"
    container_name       = "tfstate"
    key                  = "azure-native/terraform.tfstate"
  }
}

provider "azurerm" {
  features {}
}

module "foundation" {
  source      = "./modules/foundation"
  environment = var.environment
  name_prefix = var.name_prefix
  location    = var.location
}

module "functions" {
  source              = "./modules/functions"
  environment         = var.environment
  name_prefix         = var.name_prefix
  location            = var.location
  resource_group_name = module.foundation.resource_group_name
  storage_account_id  = module.foundation.storage_account_id
  cosmos_connection   = module.foundation.cosmos_connection_string
  keyvault_uri        = module.foundation.keyvault_uri
  appinsights_key     = module.observability.instrumentation_key
  appinsights_conn    = module.observability.connection_string
}

module "durable_functions" {
  source              = "./modules/durable-functions"
  environment         = var.environment
  name_prefix         = var.name_prefix
  location            = var.location
  resource_group_name = module.foundation.resource_group_name
  function_app_id     = module.functions.function_app_id
}

module "event_grid" {
  source              = "./modules/event-grid"
  environment         = var.environment
  name_prefix         = var.name_prefix
  location            = var.location
  resource_group_name = module.foundation.resource_group_name
  function_app_id     = module.functions.function_app_id
}

module "openai" {
  source              = "./modules/openai"
  environment         = var.environment
  name_prefix         = var.name_prefix
  location            = var.location
  resource_group_name = module.foundation.resource_group_name
}

module "observability" {
  source              = "./modules/observability"
  environment         = var.environment
  name_prefix         = var.name_prefix
  location            = var.location
  resource_group_name = module.foundation.resource_group_name
}
