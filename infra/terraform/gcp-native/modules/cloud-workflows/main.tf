resource "google_workflows_workflow" "agent_pipeline" {
  name            = "${var.name_prefix}-agent-pipeline"
  region          = var.region
  description     = "Internal Agents Pipeline: watcher → coding → review"
  service_account = var.service_account

  source_contents = <<-YAML
    main:
      steps:
        - telemetry_watcher:
            call: http.post
            args:
              url: ${var.watcher_function_url}
              auth:
                type: OIDC
              body: {}
            result: watcher_result
        - check_actionable:
            switch:
              - condition: $${watcher_result.body.issue_created == true}
                next: coding_agent
            next: no_action
        - coding_agent:
            call: http.post
            args:
              url: ${var.coding_function_url}
              auth:
                type: OIDC
              body: $${watcher_result.body}
            result: coding_result
        - review_agent:
            call: http.post
            args:
              url: ${var.review_function_url}
              auth:
                type: OIDC
              body: $${coding_result.body}
            result: review_result
        - done:
            return: $${review_result.body}
        - no_action:
            return:
              status: "no_actionable_signals"
  YAML

  labels = { component = "orchestration", environment = var.environment }
}

variable "project_id" { type = string }
variable "region" { type = string }
variable "environment" { type = string }
variable "name_prefix" { type = string }
variable "coding_function_url" { type = string }
variable "review_function_url" { type = string }
variable "watcher_function_url" { type = string }
variable "service_account" { type = string }

output "workflow_id" { value = google_workflows_workflow.agent_pipeline.id }
