resource "aws_cloudwatch_event_rule" "agent_schedule" {
  name                = "${var.name_prefix}-agent-schedule"
  schedule_expression = "rate(15 minutes)"
  state               = "ENABLED"
  tags                = { Component = "eventing" }
}

resource "aws_iam_role" "eventbridge_sfn" {
  name = "${var.name_prefix}-eb-sfn-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "events.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "eventbridge_sfn" {
  name = "${var.name_prefix}-eb-sfn-policy"
  role = aws_iam_role.eventbridge_sfn.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "states:StartExecution"
      Resource = var.state_machine_arn
    }]
  })
}

resource "aws_cloudwatch_event_target" "sfn" {
  rule     = aws_cloudwatch_event_rule.agent_schedule.name
  arn      = var.state_machine_arn
  role_arn = aws_iam_role.eventbridge_sfn.arn
}

resource "aws_cloudwatch_event_rule" "github_webhook" {
  name        = "${var.name_prefix}-github-webhook"
  description = "Triggers on GitHub PR events via API Gateway"

  event_pattern = jsonencode({
    source      = ["custom.github"]
    "detail-type" = ["PR Created", "PR Updated"]
  })

  tags = { Component = "eventing" }
}

resource "aws_cloudwatch_event_target" "github_sfn" {
  rule     = aws_cloudwatch_event_rule.github_webhook.name
  arn      = var.state_machine_arn
  role_arn = aws_iam_role.eventbridge_sfn.arn
}

variable "environment" { type = string }
variable "name_prefix" { type = string }
variable "state_machine_arn" { type = string }

output "rule_arn" { value = aws_cloudwatch_event_rule.agent_schedule.arn }
