data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

resource "aws_dynamodb_table" "audit" {
  name         = "${var.name_prefix}-audit-trail"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"

  attribute {
    name = "PK"
    type = "S"
  }
  attribute {
    name = "SK"
    type = "S"
  }
  attribute {
    name = "agent_name"
    type = "S"
  }
  attribute {
    name = "timestamp"
    type = "S"
  }
  attribute {
    name = "target_repo"
    type = "S"
  }

  global_secondary_index {
    name            = "by-timestamp"
    hash_key        = "agent_name"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "by-repo"
    hash_key        = "target_repo"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = { Component = "audit" }
}

resource "aws_s3_bucket" "config" {
  bucket = "${var.name_prefix}-config-${data.aws_caller_identity.current.account_id}"
  tags   = { Component = "config" }
}

resource "aws_s3_bucket_versioning" "config" {
  bucket = aws_s3_bucket.config.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "config" {
  bucket = aws_s3_bucket.config.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "config" {
  bucket                  = aws_s3_bucket.config.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_ecr_repository" "agents" {
  name                 = "${var.name_prefix}/agents"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_vpc" "agents" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = { Name = "${var.name_prefix}-vpc" }
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.agents.id
  cidr_block        = cidrsubnet(aws_vpc.agents.cidr_block, 8, count.index)
  availability_zone = data.aws_availability_zones.available.names[count.index]
  tags              = { Name = "${var.name_prefix}-private-${count.index}" }
}

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_security_group" "lambda" {
  name_prefix = "${var.name_prefix}-lambda-"
  vpc_id      = aws_vpc.agents.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.name_prefix}-lambda-sg" }
}

variable "environment" { type = string }
variable "name_prefix" { type = string }

output "audit_table_arn" { value = aws_dynamodb_table.audit.arn }
output "audit_table_name" { value = aws_dynamodb_table.audit.name }
output "config_bucket_name" { value = aws_s3_bucket.config.id }
output "ecr_repo_url" { value = aws_ecr_repository.agents.repository_url }
output "private_subnet_ids" { value = aws_subnet.private[*].id }
output "lambda_sg_id" { value = aws_security_group.lambda.id }
output "vpc_id" { value = aws_vpc.agents.id }
