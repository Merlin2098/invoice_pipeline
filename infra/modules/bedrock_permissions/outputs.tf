output "policy_arn" {
  description = "Managed policy ARN for Bedrock invocation."
  value       = aws_iam_policy.this.arn
}

output "policy_json" {
  description = "Rendered Bedrock invocation policy."
  value       = data.aws_iam_policy_document.this.json
}
