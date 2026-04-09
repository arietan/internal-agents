resource "google_project_service" "apis" {
  for_each = toset([
    "cloudfunctions.googleapis.com",
    "cloudbuild.googleapis.com",
    "run.googleapis.com",
    "workflows.googleapis.com",
    "eventarc.googleapis.com",
    "aiplatform.googleapis.com",
    "firestore.googleapis.com",
    "secretmanager.googleapis.com",
    "dlp.googleapis.com",
    "monitoring.googleapis.com",
    "cloudtrace.googleapis.com",
    "logging.googleapis.com",
    "artifactregistry.googleapis.com",
    "vpcaccess.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

resource "google_firestore_database" "agents" {
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  depends_on = [google_project_service.apis]
}

resource "google_artifact_registry_repository" "agents" {
  location      = var.region
  repository_id = "${var.name_prefix}-agents"
  format        = "DOCKER"
  description   = "Container images for internal agents"

  depends_on = [google_project_service.apis]
}

resource "google_service_account" "agents" {
  account_id   = "${var.name_prefix}-sa"
  display_name = "Internal Agents Service Account"
}

resource "google_project_iam_member" "agent_roles" {
  for_each = toset([
    "roles/datastore.user",
    "roles/secretmanager.secretAccessor",
    "roles/aiplatform.user",
    "roles/dlp.user",
    "roles/monitoring.metricWriter",
    "roles/cloudtrace.agent",
    "roles/logging.logWriter",
    "roles/run.invoker",
    "roles/workflows.invoker",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.agents.email}"
}

resource "google_vpc_access_connector" "agents" {
  name          = "${var.name_prefix}-connector"
  region        = var.region
  ip_cidr_range = "10.8.0.0/28"
  network       = "default"

  depends_on = [google_project_service.apis]
}

variable "project_id" { type = string }
variable "region" { type = string }
variable "environment" { type = string }
variable "name_prefix" { type = string }

output "artifact_registry" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.agents.repository_id}"
}
output "agent_sa_email" { value = google_service_account.agents.email }
output "vpc_connector_id" { value = google_vpc_access_connector.agents.id }
