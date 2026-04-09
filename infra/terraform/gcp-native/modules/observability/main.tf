resource "google_monitoring_dashboard" "agents" {
  dashboard_json = jsonencode({
    displayName = "${var.name_prefix} Agents Dashboard"
    gridLayout = {
      columns = 2
      widgets = [
        {
          title = "Agent Runs"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/agent_runs_total\" resource.type=\"global\""
                }
              }
            }]
          }
        },
        {
          title = "LLM Call Duration (p99)"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/agent_llm_call_duration_seconds\" resource.type=\"global\""
                  aggregation = { perSeriesAligner = "ALIGN_PERCENTILE_99" }
                }
              }
            }]
          }
        },
        {
          title = "LLM Errors"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/agent_llm_call_errors_total\" resource.type=\"global\""
                }
              }
            }]
          }
        },
        {
          title = "PRs Created"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/agent_prs_created_total\" resource.type=\"global\""
                }
              }
            }]
          }
        },
      ]
    }
  })
}

resource "google_monitoring_alert_policy" "llm_errors" {
  display_name = "${var.name_prefix} LLM Error Rate"
  combiner     = "OR"

  conditions {
    display_name = "LLM error rate > 10%"
    condition_threshold {
      filter          = "metric.type=\"custom.googleapis.com/agent_llm_call_errors_total\" resource.type=\"global\""
      comparison      = "COMPARISON_GT"
      threshold_value = 5
      duration        = "300s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = []
}

variable "project_id" { type = string }
variable "environment" { type = string }
variable "name_prefix" { type = string }
