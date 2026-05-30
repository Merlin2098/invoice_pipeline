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
  value       = "s3://${module.data_lake_bucket.bucket_name}/${local.gold_prefix}/batch_id=<batch_id>/documents.parquet"
}

output "gold_manifest_path_template" {
  description = "Expected gold manifest S3 layout outside the Athena table prefix."
  value       = "s3://${module.data_lake_bucket.bucket_name}/${local.gold_manifest_prefix}/batch_id=<batch_id>/manifest.json"
}

output "athena_results_path" {
  description = "S3 prefix used for Athena query results."
  value       = "s3://${module.data_lake_bucket.bucket_name}/${local.athena_results_prefix}/"
}

output "athena_workgroup_name" {
  description = "Athena workgroup used for Gold analytics queries."
  value       = aws_athena_workgroup.analytics.name
}

output "glue_gold_database_name" {
  description = "Glue database that catalogs Gold analytics datasets."
  value       = aws_glue_catalog_database.gold.name
}

output "glue_gold_documents_table_name" {
  description = "Glue table name for the Gold documents dataset."
  value       = aws_glue_catalog_table.gold_documents.name
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

output "extract_ocr_lambda_name" {
  description = "Lambda function name used by Step Functions to call Textract and write bronze outputs."
  value       = module.extract_ocr_lambda.lambda_name
}

output "enrich_llm_lambda_name" {
  description = "Lambda function name used by Step Functions to enrich OCR candidates and write final outputs."
  value       = module.enrich_llm_lambda.lambda_name
}

output "publish_metrics_lambda_name" {
  description = "Lambda function name used by Step Functions to publish CloudWatch metrics."
  value       = module.publish_metrics_lambda.lambda_name
}

output "consolidate_gold_lambda_name" {
  description = "Lambda function name used by the post-batch smoke finalizer."
  value       = module.consolidate_gold_lambda.lambda_name
}

output "consolidate_gold_lambda_arn" {
  description = "Lambda function ARN used by the post-batch smoke finalizer."
  value       = module.consolidate_gold_lambda.lambda_arn
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

output "budget_name" {
  description = "AWS Budget name tracking monthly cost for this project."
  value       = aws_budgets_budget.project.name
}

output "raw_ingestion_queue_url" {
  description = "FIFO queue URL that buffers S3 raw upload notifications."
  value       = module.raw_ingestion_queue.queue_url
}

output "raw_ingestion_queue_arn" {
  description = "FIFO queue ARN."
  value       = module.raw_ingestion_queue.queue_arn
}

output "raw_ingestion_dlq_url" {
  description = "Dead letter queue URL for failed raw ingestion messages."
  value       = module.raw_ingestion_queue.dlq_url
}

output "web_api_base_url" {
  description = "Base URL for the invoice pipeline web API (upload, status, history endpoints)."
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "web_api_id" {
  description = "API Gateway HTTP API ID."
  value       = aws_apigatewayv2_api.web_api.id
}

output "upload_lambda_name" {
  description = "Lambda function name for the presigned upload endpoint."
  value       = module.upload_lambda.lambda_name
}

output "invoice_status_lambda_name" {
  description = "Lambda function name for the invoice status endpoint."
  value       = module.invoice_status_lambda.lambda_name
}

output "list_invoices_lambda_name" {
  description = "Lambda function name for the invoice list endpoint."
  value       = module.list_invoices_lambda.lambda_name
}

output "glue_gold_invoice_summary_table_name" {
  description = "Glue table name for the gold_invoice_summary Athena view (SPEC-012)."
  value       = aws_glue_catalog_table.gold_invoice_summary.name
}

output "chat_lambda_name" {
  description = "Lambda function name for the POST /chat endpoint."
  value       = module.chat_lambda.lambda_name
}
