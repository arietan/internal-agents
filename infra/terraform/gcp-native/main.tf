terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  backend "gcs" {
    bucket = "internal-agents-tfstate"
    prefix = "gcp-native"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

module "foundation" {
  source      = "./modules/foundation"
  project_id  = var.project_id
  region      = var.region
  environment = var.environment
  name_prefix = var.name_prefix
}

module "cloud_functions" {
  source               = "./modules/cloud-functions"
  project_id           = var.project_id
  region               = var.region
  environment          = var.environment
  name_prefix          = var.name_prefix
  artifact_registry    = module.foundation.artifact_registry
  vpc_connector        = module.foundation.vpc_connector_id
  service_account      = module.foundation.agent_sa_email
}

module "cloud_workflows" {
  source                = "./modules/cloud-workflows"
  project_id            = var.project_id
  region                = var.region
  environment           = var.environment
  name_prefix           = var.name_prefix
  coding_function_url   = module.cloud_functions.coding_url
  review_function_url   = module.cloud_functions.review_url
  watcher_function_url  = module.cloud_functions.watcher_url
  service_account       = module.foundation.agent_sa_email
}

module "eventarc" {
  source          = "./modules/eventarc"
  project_id      = var.project_id
  region          = var.region
  environment     = var.environment
  name_prefix     = var.name_prefix
  workflow_id     = module.cloud_workflows.workflow_id
  service_account = module.foundation.agent_sa_email
}

module "vertex_ai" {
  source      = "./modules/vertex-ai"
  project_id  = var.project_id
  region      = var.region
  environment = var.environment
  name_prefix = var.name_prefix
}

module "observability" {
  source      = "./modules/observability"
  project_id  = var.project_id
  environment = var.environment
  name_prefix = var.name_prefix
}
