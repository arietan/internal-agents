variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "name_prefix" {
  description = "Prefix for all resource names"
  type        = string
  default     = "internal-agents"
}

variable "secrets_prefix" {
  description = "Prefix for Secrets Manager secrets"
  type        = string
  default     = "internal-agents/"
}
