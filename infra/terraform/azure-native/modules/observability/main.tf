resource "azurerm_log_analytics_workspace" "agents" {
  name                = "${var.name_prefix}-${var.environment}-law"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "PerGB2018"
  retention_in_days   = 90
  tags                = { Component = "observability" }
}

resource "azurerm_application_insights" "agents" {
  name                = "${var.name_prefix}-${var.environment}-ai"
  location            = var.location
  resource_group_name = var.resource_group_name
  workspace_id        = azurerm_log_analytics_workspace.agents.id
  application_type    = "other"
  tags                = { Component = "observability" }
}

resource "azurerm_monitor_action_group" "agents" {
  name                = "${var.name_prefix}-${var.environment}-ag"
  resource_group_name = var.resource_group_name
  short_name          = "iagentsalrt"
  tags                = { Component = "observability" }
}

resource "azurerm_monitor_metric_alert" "llm_errors" {
  name                = "${var.name_prefix}-${var.environment}-llm-errors"
  resource_group_name = var.resource_group_name
  scopes              = [azurerm_application_insights.agents.id]
  severity            = 2
  frequency           = "PT5M"
  window_size         = "PT15M"

  criteria {
    metric_namespace = "azure.applicationinsights"
    metric_name      = "customMetrics/agent_llm_call_errors_total"
    aggregation      = "Count"
    operator         = "GreaterThan"
    threshold        = 5
  }

  action {
    action_group_id = azurerm_monitor_action_group.agents.id
  }

  tags = { Component = "observability" }
}

variable "environment" { type = string }
variable "name_prefix" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }

output "instrumentation_key" { value = azurerm_application_insights.agents.instrumentation_key }
output "connection_string" { value = azurerm_application_insights.agents.connection_string }
