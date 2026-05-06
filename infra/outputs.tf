output "artifact_bucket_name" {
  description = "S3 bucket used for packaged Lambda and Glue artifacts."
  value       = module.storage.artifact_bucket_name
}

output "data_lake_bucket_name" {
  description = "S3 data lake bucket for raw, bronze, silver, gold, and metrics."
  value       = module.storage.data_lake_bucket_name
}

output "prevalidation_lambda_arn" {
  description = "Lambda ARN used for file prevalidation."
  value       = module.compute.prevalidation_lambda_arn
}

output "publish_metrics_lambda_arn" {
  description = "Lambda ARN used for publishing run metrics."
  value       = module.compute.publish_metrics_lambda_arn
}

output "normalize_job_name" {
  description = "Glue job name for bronze to silver normalization."
  value       = module.compute.normalize_job_name
}

output "consolidate_job_name" {
  description = "Glue job name for silver to gold consolidation."
  value       = module.compute.consolidate_job_name
}

output "state_machine_arn" {
  description = "Step Functions state machine ARN."
  value       = module.orchestration.state_machine_arn
}
