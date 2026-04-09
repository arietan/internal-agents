resource "aws_iam_role" "sfn" {
  name = "${var.name_prefix}-sfn-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "states.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "sfn_invoke" {
  name = "${var.name_prefix}-sfn-invoke"
  role = aws_iam_role.sfn.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = [var.coding_lambda_arn, var.review_lambda_arn, var.watcher_lambda_arn]
    }]
  })
}

resource "aws_sfn_state_machine" "agent_pipeline" {
  name     = "${var.name_prefix}-agent-pipeline"
  role_arn = aws_iam_role.sfn.arn

  definition = jsonencode({
    Comment = "Internal Agents Pipeline — self-healing → coding → review"
    StartAt = "TelemetryWatcher"
    States = {
      TelemetryWatcher = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = var.watcher_lambda_arn
          "Payload.$"  = "$"
        }
        ResultPath = "$.watcher_result"
        Next       = "CheckActionable"
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "WatcherFailed"
          ResultPath  = "$.error"
        }]
      }
      CheckActionable = {
        Type = "Choice"
        Choices = [{
          Variable     = "$.watcher_result.Payload.issue_created"
          BooleanEquals = true
          Next         = "CodingAgent"
        }]
        Default = "NoAction"
      }
      CodingAgent = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = var.coding_lambda_arn
          "Payload.$"  = "$"
        }
        ResultPath = "$.coding_result"
        Next       = "ReviewAgent"
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "CodingFailed"
          ResultPath  = "$.error"
        }]
      }
      ReviewAgent = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = var.review_lambda_arn
          "Payload.$"  = "$"
        }
        ResultPath = "$.review_result"
        End        = true
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "ReviewFailed"
          ResultPath  = "$.error"
        }]
      }
      NoAction       = { Type = "Succeed", Comment = "No actionable telemetry" }
      WatcherFailed  = { Type = "Fail", Cause = "Telemetry watcher failed" }
      CodingFailed   = { Type = "Fail", Cause = "Coding agent failed" }
      ReviewFailed   = { Type = "Fail", Cause = "Review agent failed" }
    }
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tags = { Component = "orchestration" }
}

resource "aws_cloudwatch_log_group" "sfn" {
  name              = "/aws/states/${var.name_prefix}-agent-pipeline"
  retention_in_days = 90
}

variable "environment" { type = string }
variable "name_prefix" { type = string }
variable "coding_lambda_arn" { type = string }
variable "review_lambda_arn" { type = string }
variable "watcher_lambda_arn" { type = string }

output "state_machine_arn" { value = aws_sfn_state_machine.agent_pipeline.arn }
