terraform {
  required_version = ">= 1.5"
}

variable "cloud" {
  description = "Which managed K8s cluster to provision: eks, aks, or gke"
  type        = string
  validation {
    condition     = contains(["eks", "aks", "gke"], var.cloud)
    error_message = "Must be one of: eks, aks, gke"
  }
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "name_prefix" {
  description = "Prefix for all resource names"
  type        = string
  default     = "internal-agents"
}

module "eks" {
  source      = "./modules/eks"
  count       = var.cloud == "eks" ? 1 : 0
  environment = var.environment
  name_prefix = var.name_prefix
}

module "aks" {
  source      = "./modules/aks"
  count       = var.cloud == "aks" ? 1 : 0
  environment = var.environment
  name_prefix = var.name_prefix
}

module "gke" {
  source      = "./modules/gke"
  count       = var.cloud == "gke" ? 1 : 0
  environment = var.environment
  name_prefix = var.name_prefix
}
