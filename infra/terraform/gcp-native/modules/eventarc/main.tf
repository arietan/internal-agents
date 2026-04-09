resource "google_cloud_scheduler_job" "agent_schedule" {
  name     = "${var.name_prefix}-agent-schedule"
  region   = var.region
  schedule = "*/15 * * * *"

  http_target {
    uri         = "https://workflowexecutions.googleapis.com/v1/${var.workflow_id}/executions"
    http_method = "POST"
    body        = base64encode("{}")
    headers     = { "Content-Type" = "application/json" }

    oauth_token {
      service_account_email = var.service_account
    }
  }
}

variable "project_id" { type = string }
variable "region" { type = string }
variable "environment" { type = string }
variable "name_prefix" { type = string }
variable "workflow_id" { type = string }
variable "service_account" { type = string }
