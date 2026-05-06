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
  description = "S3 key of the placeholder Lambda deployment package in the artifact bucket."
  type        = string
  default     = "artifacts/lambda/raw_ingestion.zip"
}

variable "lambda_runtime" {
  description = "Runtime for the placeholder ingestion Lambda."
  type        = string
  default     = "python3.11"
}

variable "lambda_handler" {
  description = "Handler for the placeholder ingestion Lambda."
  type        = string
  default     = "src.aws.lambda_handlers.control_plane.handle_raw_ingestion"
}

variable "lambda_timeout_seconds" {
  description = "Timeout for the placeholder ingestion Lambda."
  type        = number
  default     = 60
}

variable "lambda_memory_size" {
  description = "Memory size for the placeholder ingestion Lambda."
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
  description = "Bedrock model ID reserved for future structured normalization."
  type        = string
  default     = "bedrock-model-id"
}

variable "tags" {
  description = "Additional tags merged into the default tag set."
  type        = map(string)
  default     = {}
}
