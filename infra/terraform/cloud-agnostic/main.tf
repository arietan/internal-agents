terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.80"
    }
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region                      = "us-east-1"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
}

provider "azurerm" {
  features {}
  skip_provider_registration = true
}

provider "google" {
  project = "placeholder"
  region  = "us-central1"
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
