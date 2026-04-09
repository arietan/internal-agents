terraform {
  required_providers {
    google = { source = "hashicorp/google", version = "~> 5.0" }
  }
}

variable "environment" { type = string }
variable "name_prefix" { type = string }
variable "project_id" {
  type    = string
  default = ""
}
variable "region" {
  type    = string
  default = "us-central1"
}
variable "machine_type" {
  type    = string
  default = "e2-standard-4"
}
variable "node_count" {
  type    = number
  default = 3
}

resource "google_container_cluster" "main" {
  name     = "${var.name_prefix}-${var.environment}-gke"
  location = var.region

  initial_node_count       = 1
  remove_default_node_pool = true

  networking_mode = "VPC_NATIVE"
  ip_allocation_policy {}

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }
}

resource "google_container_node_pool" "agents" {
  name       = "agents"
  location   = var.region
  cluster    = google_container_cluster.main.name
  node_count = var.node_count

  node_config {
    machine_type = var.machine_type
    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }

  autoscaling {
    min_node_count = 1
    max_node_count = var.node_count * 2
  }
}

output "cluster_name" { value = google_container_cluster.main.name }
output "cluster_endpoint" { value = google_container_cluster.main.endpoint }
