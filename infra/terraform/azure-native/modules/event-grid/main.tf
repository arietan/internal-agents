resource "azurerm_eventgrid_system_topic" "agents" {
  name                   = "${var.name_prefix}-${var.environment}-topic"
  resource_group_name    = var.resource_group_name
  location               = var.location
  source_arm_resource_id = var.function_app_id
  topic_type             = "Microsoft.Web.Sites"
  tags                   = { Component = "eventing" }
}

variable "environment" { type = string }
variable "name_prefix" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "function_app_id" { type = string }
