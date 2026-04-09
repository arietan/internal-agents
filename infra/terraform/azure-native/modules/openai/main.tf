resource "azurerm_cognitive_account" "openai" {
  name                = "${var.name_prefix}-${var.environment}-aoai"
  location            = var.location
  resource_group_name = var.resource_group_name
  kind                = "OpenAI"
  sku_name            = "S0"
  tags                = { Component = "llm" }
}

resource "azurerm_cognitive_deployment" "gpt4o" {
  name                 = "gpt-4o"
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = "gpt-4o"
    version = "2024-08-06"
  }

  sku {
    name     = "Standard"
    capacity = 30
  }
}

variable "environment" { type = string }
variable "name_prefix" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }

output "endpoint" { value = azurerm_cognitive_account.openai.endpoint }
