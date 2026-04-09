resource "aws_bedrock_guardrail" "agent_guardrail" {
  name        = "${var.name_prefix}-guardrail"
  description = "PII, credential, and content safety guardrail for internal agents"

  blocked_input_messaging  = "Input blocked by guardrail policy."
  blocked_outputs_messaging = "Output blocked by guardrail policy."

  sensitive_information_policy_config {
    pii_entities_config {
      action = "BLOCK"
      type   = "EMAIL"
    }
    pii_entities_config {
      action = "BLOCK"
      type   = "PHONE"
    }
    pii_entities_config {
      action = "BLOCK"
      type   = "US_SOCIAL_SECURITY_NUMBER"
    }
    pii_entities_config {
      action = "BLOCK"
      type   = "CREDIT_DEBIT_CARD_NUMBER"
    }

    regexes_config {
      name        = "aws-key"
      description = "AWS access key pattern"
      pattern     = "AKIA[A-Z0-9]{16}"
      action      = "BLOCK"
    }
    regexes_config {
      name        = "github-pat"
      description = "GitHub personal access token"
      pattern     = "ghp_[A-Za-z0-9_]{36}"
      action      = "BLOCK"
    }
  }

  tags = { Component = "dlp" }
}

resource "aws_bedrock_guardrail_version" "v1" {
  guardrail_arn = aws_bedrock_guardrail.agent_guardrail.guardrail_arn
  description   = "Initial guardrail version"
}

resource "aws_ssm_parameter" "guardrail_id" {
  name  = "/internal-agents/BEDROCK_GUARDRAIL_ID"
  type  = "String"
  value = aws_bedrock_guardrail.agent_guardrail.guardrail_id
}

resource "aws_ssm_parameter" "guardrail_version" {
  name  = "/internal-agents/BEDROCK_GUARDRAIL_VERSION"
  type  = "String"
  value = aws_bedrock_guardrail_version.v1.version
}

variable "environment" { type = string }
variable "name_prefix" { type = string }

output "guardrail_id" { value = aws_bedrock_guardrail.agent_guardrail.guardrail_id }
