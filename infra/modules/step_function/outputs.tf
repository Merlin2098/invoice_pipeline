output "state_machine_arn" {
  description = "Step Functions state machine ARN."
  value       = aws_sfn_state_machine.this.arn
}

output "state_machine_name" {
  description = "Step Functions state machine name."
  value       = aws_sfn_state_machine.this.name
}

output "role_name" {
  description = "IAM role name assumed by the state machine."
  value       = aws_iam_role.this.name
}

output "role_arn" {
  description = "IAM role ARN assumed by the state machine."
  value       = aws_iam_role.this.arn
}

output "log_group_name" {
  description = "CloudWatch log group name used by the state machine."
  value       = aws_cloudwatch_log_group.this.name
}
