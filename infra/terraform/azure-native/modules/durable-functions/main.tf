resource "azurerm_storage_account" "durable" {
  name                     = "${var.name_prefix}${var.environment}dur"
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  tags                     = { Component = "orchestration" }
}

variable "environment" { type = string }
variable "name_prefix" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "function_app_id" { type = string }
