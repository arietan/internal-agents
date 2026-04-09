data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

resource "aws_iam_role" "agent_lambda" {
  name = "${var.name_prefix}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "lambda_permissions" {
  name = "${var.name_prefix}-lambda-policy"
  role = aws_iam_role.agent_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:*"
      },
      {
        Effect   = "Allow"
        Action   = ["ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DeleteNetworkInterface"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan"]
        Resource = [var.audit_table_arn, "${var.audit_table_arn}/index/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:ListBucket"]
        Resource = ["arn:aws:s3:::${var.config_bucket}", "arn:aws:s3:::${var.config_bucket}/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = "arn:aws:secretsmanager:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:secret:${var.secrets_prefix}*"
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream",
          "bedrock:ApplyGuardrail", "bedrock:ListFoundationModels",
        ]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParametersByPath"]
        Resource = "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter/internal-agents/*"
      },
      {
        Effect   = "Allow"
        Action   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
        Resource = "*"
      },
    ]
  })
}

locals {
  common_env = {
    CLOUD_PROVIDER  = "aws"
    AUDIT_TABLE     = split(":", var.audit_table_arn)[length(split(":", var.audit_table_arn)) - 1]
    CONFIG_BUCKET   = var.config_bucket
    SECRETS_PREFIX  = var.secrets_prefix
    SSM_PREFIX      = "/internal-agents/"
    XRAY_ENABLED    = "true"
    CW_NAMESPACE    = "InternalAgents"
  }
  timeout = 900
  memory  = 512
}

resource "aws_lambda_function" "coding_agent" {
  function_name = "${var.name_prefix}-coding-agent"
  role          = aws_iam_role.agent_lambda.arn
  package_type  = "Image"
  image_uri     = "${var.ecr_repo_url}:coding-agent-latest"
  timeout       = local.timeout
  memory_size   = local.memory

  vpc_config {
    subnet_ids         = var.vpc_subnet_ids
    security_group_ids = var.vpc_sg_ids
  }

  environment { variables = local.common_env }

  tracing_config { mode = "Active" }

  tags = { Agent = "coding-agent" }
}

resource "aws_lambda_function" "review_agent" {
  function_name = "${var.name_prefix}-review-agent"
  role          = aws_iam_role.agent_lambda.arn
  package_type  = "Image"
  image_uri     = "${var.ecr_repo_url}:review-agent-latest"
  timeout       = local.timeout
  memory_size   = local.memory

  vpc_config {
    subnet_ids         = var.vpc_subnet_ids
    security_group_ids = var.vpc_sg_ids
  }

  environment { variables = local.common_env }

  tracing_config { mode = "Active" }

  tags = { Agent = "review-agent" }
}

resource "aws_lambda_function" "telemetry_watcher" {
  function_name = "${var.name_prefix}-telemetry-watcher"
  role          = aws_iam_role.agent_lambda.arn
  package_type  = "Image"
  image_uri     = "${var.ecr_repo_url}:watcher-latest"
  timeout       = 300
  memory_size   = 256

  vpc_config {
    subnet_ids         = var.vpc_subnet_ids
    security_group_ids = var.vpc_sg_ids
  }

  environment { variables = local.common_env }

  tracing_config { mode = "Active" }

  tags = { Agent = "telemetry-watcher" }
}

resource "aws_cloudwatch_log_group" "coding" {
  name              = "/aws/lambda/${aws_lambda_function.coding_agent.function_name}"
  retention_in_days = 90
}

resource "aws_cloudwatch_log_group" "review" {
  name              = "/aws/lambda/${aws_lambda_function.review_agent.function_name}"
  retention_in_days = 90
}

resource "aws_cloudwatch_log_group" "watcher" {
  name              = "/aws/lambda/${aws_lambda_function.telemetry_watcher.function_name}"
  retention_in_days = 90
}

variable "environment" { type = string }
variable "name_prefix" { type = string }
variable "vpc_subnet_ids" { type = list(string) }
variable "vpc_sg_ids" { type = list(string) }
variable "ecr_repo_url" { type = string }
variable "audit_table_arn" { type = string }
variable "config_bucket" { type = string }
variable "secrets_prefix" { type = string }

output "coding_agent_arn" { value = aws_lambda_function.coding_agent.arn }
output "review_agent_arn" { value = aws_lambda_function.review_agent.arn }
output "watcher_lambda_arn" { value = aws_lambda_function.telemetry_watcher.arn }
output "log_group_names" {
  value = [
    aws_cloudwatch_log_group.coding.name,
    aws_cloudwatch_log_group.review.name,
    aws_cloudwatch_log_group.watcher.name,
  ]
}
