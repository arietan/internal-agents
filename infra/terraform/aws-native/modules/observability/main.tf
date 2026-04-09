resource "aws_cloudwatch_dashboard" "agents" {
  dashboard_name = "${var.name_prefix}-dashboard"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Agent Runs & PRs Created"
          metrics = [
            ["InternalAgents", "AgentRuns", { stat = "Sum", period = 300 }],
            ["InternalAgents", "PRsCreated", { stat = "Sum", period = 300 }],
            ["InternalAgents", "ReviewsPosted", { stat = "Sum", period = 300 }],
          ]
          view   = "timeSeries"
          region = data.aws_region.current.name
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "LLM Call Latency"
          metrics = [["InternalAgents", "LLMDuration", { stat = "p99", period = 300 }]]
          view    = "timeSeries"
          region  = data.aws_region.current.name
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title   = "LLM Errors"
          metrics = [["InternalAgents", "LLMErrors", { stat = "Sum", period = 300 }]]
          view    = "timeSeries"
          region  = data.aws_region.current.name
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title   = "LLM Tokens Consumed"
          metrics = [["InternalAgents", "LLMTokens", { stat = "Sum", period = 3600 }]]
          view    = "timeSeries"
          region  = data.aws_region.current.name
        }
      },
    ]
  })
}

data "aws_region" "current" {}

resource "aws_cloudwatch_metric_alarm" "llm_error_rate" {
  alarm_name          = "${var.name_prefix}-llm-error-rate"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  threshold           = 0.1
  alarm_description   = "LLM error rate exceeded 10%"

  metric_query {
    id          = "error_rate"
    expression  = "errors/calls"
    label       = "Error Rate"
    return_data = true
  }

  metric_query {
    id = "errors"
    metric {
      metric_name = "LLMErrors"
      namespace   = "InternalAgents"
      period      = 300
      stat        = "Sum"
    }
  }

  metric_query {
    id = "calls"
    metric {
      metric_name = "LLMCalls"
      namespace   = "InternalAgents"
      period      = 300
      stat        = "Sum"
    }
  }

  tags = { Component = "observability" }
}

resource "aws_cloudwatch_log_metric_filter" "agent_errors" {
  count          = length(var.lambda_log_groups)
  name           = "${var.name_prefix}-errors-${count.index}"
  log_group_name = var.lambda_log_groups[count.index]
  pattern        = "?ERROR ?Exception ?Traceback"

  metric_transformation {
    name      = "AgentErrors"
    namespace = "InternalAgents"
    value     = "1"
  }
}

variable "environment" { type = string }
variable "name_prefix" { type = string }
variable "lambda_log_groups" { type = list(string) }

output "dashboard_url" {
  value = "https://${data.aws_region.current.name}.console.aws.amazon.com/cloudwatch/home#dashboards:name=${aws_cloudwatch_dashboard.agents.dashboard_name}"
}
