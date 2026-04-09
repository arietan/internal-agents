terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "internal-agents-tfstate"
    key            = "aws-native/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "internal-agents"
      Environment = var.environment
      ManagedBy   = "terraform"
      CostCenter  = "ai-platform"
    }
  }
}

module "foundation" {
  source      = "./modules/foundation"
  environment = var.environment
  name_prefix = var.name_prefix
}

module "lambdas" {
  source          = "./modules/lambdas"
  environment     = var.environment
  name_prefix     = var.name_prefix
  vpc_subnet_ids  = module.foundation.private_subnet_ids
  vpc_sg_ids      = [module.foundation.lambda_sg_id]
  ecr_repo_url    = module.foundation.ecr_repo_url
  audit_table_arn = module.foundation.audit_table_arn
  config_bucket   = module.foundation.config_bucket_name
  secrets_prefix  = var.secrets_prefix
}

module "step_functions" {
  source            = "./modules/step-functions"
  environment       = var.environment
  name_prefix       = var.name_prefix
  coding_lambda_arn = module.lambdas.coding_agent_arn
  review_lambda_arn = module.lambdas.review_agent_arn
  watcher_lambda_arn = module.lambdas.watcher_lambda_arn
}

module "eventbridge" {
  source           = "./modules/eventbridge"
  environment      = var.environment
  name_prefix      = var.name_prefix
  state_machine_arn = module.step_functions.state_machine_arn
}

module "bedrock" {
  source      = "./modules/bedrock"
  environment = var.environment
  name_prefix = var.name_prefix
}

module "observability" {
  source      = "./modules/observability"
  environment = var.environment
  name_prefix = var.name_prefix
  lambda_log_groups = module.lambdas.log_group_names
}
