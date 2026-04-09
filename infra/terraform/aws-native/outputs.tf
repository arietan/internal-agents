output "state_machine_arn" {
  value = module.step_functions.state_machine_arn
}

output "eventbridge_rule_arn" {
  value = module.eventbridge.rule_arn
}

output "audit_table_name" {
  value = module.foundation.audit_table_name
}

output "config_bucket" {
  value = module.foundation.config_bucket_name
}

output "dashboard_url" {
  value = module.observability.dashboard_url
}
