output "policy_arn" {
  description = "Managed policy ARN for Textract and S3 bronze permissions."
  value       = aws_iam_policy.this.arn
}

output "policy_json" {
  description = "Rendered policy JSON document."
  value       = data.aws_iam_policy_document.this.json
}
