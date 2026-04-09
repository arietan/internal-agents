locals {
  common_env = {
    CLOUD_PROVIDER       = "gcp"
    GCP_PROJECT          = var.project_id
    GCP_LOCATION         = var.region
    FIRESTORE_COLLECTION = "agent-audit-trail"
  }
}

resource "google_cloudfunctions2_function" "coding_agent" {
  name     = "${var.name_prefix}-coding-agent"
  location = var.region

  build_config {
    runtime     = "python312"
    entry_point = "coding_agent_handler"
    source {
      storage_source {
        bucket = "${var.name_prefix}-source"
        object = "coding-agent.zip"
      }
    }
  }

  service_config {
    max_instance_count    = 5
    min_instance_count    = 0
    available_memory      = "1Gi"
    timeout_seconds       = 540
    service_account_email = var.service_account

    environment_variables = local.common_env

    vpc_connector                 = var.vpc_connector
    vpc_connector_egress_settings = "PRIVATE_RANGES_ONLY"
  }

  labels = { agent = "coding-agent", environment = var.environment }
}

resource "google_cloudfunctions2_function" "review_agent" {
  name     = "${var.name_prefix}-review-agent"
  location = var.region

  build_config {
    runtime     = "python312"
    entry_point = "review_agent_handler"
    source {
      storage_source {
        bucket = "${var.name_prefix}-source"
        object = "review-agent.zip"
      }
    }
  }

  service_config {
    max_instance_count    = 5
    min_instance_count    = 0
    available_memory      = "1Gi"
    timeout_seconds       = 540
    service_account_email = var.service_account

    environment_variables = local.common_env

    vpc_connector                 = var.vpc_connector
    vpc_connector_egress_settings = "PRIVATE_RANGES_ONLY"
  }

  labels = { agent = "review-agent", environment = var.environment }
}

resource "google_cloudfunctions2_function" "watcher" {
  name     = "${var.name_prefix}-telemetry-watcher"
  location = var.region

  build_config {
    runtime     = "python312"
    entry_point = "watcher_handler"
    source {
      storage_source {
        bucket = "${var.name_prefix}-source"
        object = "watcher.zip"
      }
    }
  }

  service_config {
    max_instance_count    = 2
    min_instance_count    = 0
    available_memory      = "512Mi"
    timeout_seconds       = 300
    service_account_email = var.service_account

    environment_variables = local.common_env

    vpc_connector                 = var.vpc_connector
    vpc_connector_egress_settings = "PRIVATE_RANGES_ONLY"
  }

  labels = { agent = "telemetry-watcher", environment = var.environment }
}

variable "project_id" { type = string }
variable "region" { type = string }
variable "environment" { type = string }
variable "name_prefix" { type = string }
variable "artifact_registry" { type = string }
variable "vpc_connector" { type = string }
variable "service_account" { type = string }

output "coding_url" { value = google_cloudfunctions2_function.coding_agent.service_config[0].uri }
output "review_url" { value = google_cloudfunctions2_function.review_agent.service_config[0].uri }
output "watcher_url" { value = google_cloudfunctions2_function.watcher.service_config[0].uri }
