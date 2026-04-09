variable "environment" { type = string }
variable "name_prefix" { type = string }
variable "location" {
  type    = string
  default = "eastus2"
}
variable "node_vm_size" {
  type    = string
  default = "Standard_D4s_v3"
}
variable "node_count" {
  type    = number
  default = 3
}

resource "azurerm_resource_group" "main" {
  name     = "${var.name_prefix}-${var.environment}-rg"
  location = var.location
}

resource "azurerm_kubernetes_cluster" "main" {
  name                = "${var.name_prefix}-${var.environment}-aks"
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = "${var.name_prefix}-${var.environment}"

  default_node_pool {
    name       = "agents"
    node_count = var.node_count
    vm_size    = var.node_vm_size
  }

  identity { type = "SystemAssigned" }

  network_profile {
    network_plugin = "azure"
    network_policy = "calico"
  }

  tags = { Environment = var.environment }
}

output "cluster_name" { value = azurerm_kubernetes_cluster.main.name }
output "kube_config" {
  value     = azurerm_kubernetes_cluster.main.kube_config_raw
  sensitive = true
}
