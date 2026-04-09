resource "google_project_service" "vertex" {
  service            = "aiplatform.googleapis.com"
  disable_on_destroy = false
}

variable "project_id" { type = string }
variable "region" { type = string }
variable "environment" { type = string }
variable "name_prefix" { type = string }
