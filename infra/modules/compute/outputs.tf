output "prevalidation_lambda_arn" {
  value = aws_lambda_function.prevalidation.arn
}

output "publish_metrics_lambda_arn" {
  value = aws_lambda_function.publish_metrics.arn
}

output "normalize_job_name" {
  value = aws_glue_job.normalize.name
}

output "consolidate_job_name" {
  value = aws_glue_job.consolidate.name
}

