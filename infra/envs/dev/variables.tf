variable "project_name" {
  description = "Project name used in resource naming."
  type        = string
  default     = "invoice-pipeline"
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "dev"
}

variable "owner" {
  description = "Owner tag value applied to all resources."
  type        = string
  default     = "data-engineering"
}

variable "aws_region" {
  description = "AWS region where resources are deployed."
  type        = string
  default     = "us-east-1"
}

variable "artifact_bucket_suffix" {
  description = "Suffix appended to the generated artifact bucket name."
  type        = string
  default     = "artifacts"
}

variable "data_lake_bucket_suffix" {
  description = "Suffix appended to the generated data lake bucket name."
  type        = string
  default     = "lake"
}

variable "artifact_bucket_name_override" {
  description = "Optional explicit artifact bucket name override."
  type        = string
  default     = null
  nullable    = true
}

variable "data_lake_bucket_name_override" {
  description = "Optional explicit data lake bucket name override."
  type        = string
  default     = null
  nullable    = true
}

variable "force_destroy" {
  description = "Allow S3 bucket deletion when non-empty. Intended only for dev environments."
  type        = bool
  default     = false
}

variable "lambda_package_s3_key" {
  description = "S3 key of the Lambda deployment package in the artifact bucket."
  type        = string
  default     = "artifacts/lambda/control_plane_bundle.zip"
}

variable "lambda_runtime" {
  description = "Runtime for all control-plane Lambdas."
  type        = string
  default     = "python3.11"
}

variable "lambda_handler" {
  description = "Deprecated generic Lambda handler. Use the dedicated handler variables below."
  type        = string
  default     = "src.aws.lambda_handlers.control_plane.start_raw_ingestion"
}

variable "raw_dispatch_handler" {
  description = "Handler for the raw S3 dispatcher Lambda."
  type        = string
  default     = "src.aws.lambda_handlers.control_plane.start_raw_ingestion"
}

variable "validate_input_handler" {
  description = "Handler for the validation Lambda."
  type        = string
  default     = "src.aws.lambda_handlers.control_plane.validate_input"
}

variable "process_document_handler" {
  description = "Handler for the document processing Lambda."
  type        = string
  default     = "src.aws.lambda_handlers.control_plane.process_document"
}

variable "publish_metrics_handler" {
  description = "Handler for the metrics publishing Lambda."
  type        = string
  default     = "src.aws.lambda_handlers.control_plane.publish_run_metrics"
}

variable "lambda_timeout_seconds" {
  description = "Timeout for the control-plane Lambdas."
  type        = number
  default     = 60
}

variable "lambda_memory_size" {
  description = "Memory size for the control-plane Lambdas."
  type        = number
  default     = 256
}

variable "lambda_log_retention_in_days" {
  description = "Retention period for Lambda logs."
  type        = number
  default     = 30
}

variable "step_function_log_retention_in_days" {
  description = "Retention period for Step Functions logs."
  type        = number
  default     = 30
}

variable "raw_prefix" {
  description = "Canonical raw prefix inside the data lake bucket."
  type        = string
  default     = "raw"
}

variable "bronze_prefix" {
  description = "Canonical bronze prefix inside the data lake bucket."
  type        = string
  default     = "bronze/textract-json"
}

variable "silver_valid_prefix" {
  description = "Canonical silver valid prefix inside the data lake bucket."
  type        = string
  default     = "silver/valid"
}

variable "silver_rejected_prefix" {
  description = "Canonical silver rejected prefix inside the data lake bucket."
  type        = string
  default     = "silver/rejected"
}

variable "gold_prefix" {
  description = "Canonical gold prefix inside the data lake bucket."
  type        = string
  default     = "gold/documents"
}

variable "errors_prefix" {
  description = "Canonical technical errors prefix inside the data lake bucket."
  type        = string
  default     = "errors"
}

variable "raw_trigger_suffix" {
  description = "Optional suffix filter for raw upload notifications, such as .pdf."
  type        = string
  default     = null
  nullable    = true
}

variable "bedrock_model_id" {
  description = "Bedrock model ID used for structured normalization when Textract extraction is incomplete."
  type        = string
  default     = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
}

variable "cloudwatch_namespace" {
  description = "CloudWatch namespace used by the metrics publisher Lambda."
  type        = string
  default     = "InvoicePipeline"
}

variable "tags" {
  description = "Additional tags merged into the default tag set."
  type        = map(string)
  default     = {}
}

variable "budget_alert_email" {
  description = "Email address that receives AWS Budget threshold notifications."
  type        = string
}
