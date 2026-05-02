output "artifact_bucket_name" {
  description = "S3 bucket used for packaged runtime artifacts."
  value       = aws_s3_bucket.artifacts.bucket
}

output "artifact_bundle_s3_uri" {
  description = "S3 URI of the packaged runtime artifact."
  value       = "s3://${aws_s3_bucket.artifacts.bucket}/${aws_s3_object.artifact_bundle.key}"
}

output "data_job_execution_role_arn" {
  description = "IAM role ARN for Glue or other batch data jobs."
  value       = aws_iam_role.data_job_execution.arn
}
