output "artifact_bucket_name" {
  description = "Artifact bucket name for Lambda deployment packages."
  value       = module.artifact_bucket.bucket_name
}

output "artifact_bucket_arn" {
  description = "Artifact bucket ARN."
  value       = module.artifact_bucket.bucket_arn
}

output "data_lake_bucket_name" {
  description = "Data lake bucket name."
  value       = module.data_lake_bucket.bucket_name
}

output "data_lake_bucket_arn" {
  description = "Data lake bucket ARN."
  value       = module.data_lake_bucket.bucket_arn
}

output "raw_path_template" {
  description = "Expected raw S3 layout."
  value       = "s3://${module.data_lake_bucket.bucket_name}/${local.raw_prefix}/run_id=<run_id>/"
}

output "bronze_path_template" {
  description = "Expected bronze S3 layout."
  value       = "s3://${module.data_lake_bucket.bucket_name}/${local.bronze_prefix}/run_id=<run_id>/<document_id>.json"
}

output "silver_valid_path_template" {
  description = "Expected silver valid S3 layout."
  value       = "s3://${module.data_lake_bucket.bucket_name}/${local.silver_valid_prefix}/run_id=<run_id>/<document_id>.json"
}

output "silver_rejected_path_template" {
  description = "Expected silver rejected S3 layout."
  value       = "s3://${module.data_lake_bucket.bucket_name}/${local.silver_rejected_prefix}/run_id=<run_id>/<document_id>.json"
}

output "gold_path_template" {
  description = "Expected gold S3 layout."
  value       = "s3://${module.data_lake_bucket.bucket_name}/${local.gold_prefix}/run_date=YYYY-MM-DD/documents.parquet"
}

output "errors_path_template" {
  description = "Expected technical errors S3 layout."
  value       = "s3://${module.data_lake_bucket.bucket_name}/${local.errors_prefix}/"
}

output "raw_dispatch_lambda_name" {
  description = "Lambda function name that receives raw S3 upload notifications."
  value       = module.raw_dispatch_lambda.lambda_name
}

output "raw_dispatch_lambda_arn" {
  description = "Lambda function ARN that receives raw S3 upload notifications."
  value       = module.raw_dispatch_lambda.lambda_arn
}

output "validate_input_lambda_name" {
  description = "Lambda function name used by Step Functions to validate inputs."
  value       = module.validate_input_lambda.lambda_name
}

output "process_document_lambda_name" {
  description = "Lambda function name used by Step Functions to call Textract and write bronze/silver outputs."
  value       = module.process_document_lambda.lambda_name
}

output "publish_metrics_lambda_name" {
  description = "Lambda function name used by Step Functions to publish CloudWatch metrics."
  value       = module.publish_metrics_lambda.lambda_name
}

output "state_machine_name" {
  description = "Document pipeline Step Functions state machine name."
  value       = module.invoice_pipeline_state_machine.state_machine_name
}

output "state_machine_arn" {
  description = "Document pipeline Step Functions state machine ARN."
  value       = module.invoice_pipeline_state_machine.state_machine_arn
}

output "step_function_role_name" {
  description = "IAM role name used by the Step Functions state machine."
  value       = module.invoice_pipeline_state_machine.role_name
}

output "textract_policy_arn" {
  description = "Managed policy ARN attached to the processing role for Textract access."
  value       = module.textract_permissions.policy_arn
}

output "bedrock_policy_arn" {
  description = "Managed policy ARN attached to the processing role for future Bedrock access."
  value       = module.bedrock_permissions.policy_arn
}
