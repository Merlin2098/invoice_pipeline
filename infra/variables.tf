variable "project_name" {
  description = "Project name used in AWS resource naming."
  type        = string
  default     = "invoice-pipeline"
}

variable "environment" {
  description = "Deployment environment."
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region for the deployment."
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

variable "lambda_package_s3_key" {
  description = "S3 object key of the packaged Lambda bundle inside the artifact bucket."
  type        = string
  default     = "artifacts/data_platform_bundle.zip"
}

variable "normalize_script_s3_key" {
  description = "S3 object key of the Glue normalization script inside the artifact bucket."
  type        = string
  default     = "glue/normalize_documents.py"
}

variable "consolidate_script_s3_key" {
  description = "S3 object key of the Glue gold consolidation script inside the artifact bucket."
  type        = string
  default     = "glue/consolidate_gold.py"
}

variable "raw_prefix" {
  description = "Prefix for raw input objects."
  type        = string
  default     = "raw"
}

variable "bronze_prefix" {
  description = "Prefix for bronze technical evidence."
  type        = string
  default     = "bronze/textract-json"
}

variable "silver_valid_prefix" {
  description = "Prefix for accepted or warning silver records."
  type        = string
  default     = "silver/valid"
}

variable "silver_rejected_prefix" {
  description = "Prefix for rejected silver records."
  type        = string
  default     = "silver/rejected"
}

variable "gold_prefix" {
  description = "Prefix for gold parquet outputs."
  type        = string
  default     = "gold/documents"
}

variable "metrics_prefix" {
  description = "Prefix for run manifests and metrics artifacts."
  type        = string
  default     = "metrics"
}

variable "bedrock_model_id" {
  description = "Bedrock model identifier used only for ambiguity resolution."
  type        = string
  default     = "bedrock-model-id"
}

variable "cloudwatch_namespace" {
  description = "Namespace for custom CloudWatch metrics."
  type        = string
  default     = "InvoicePipeline"
}

variable "state_machine_log_group_name" {
  description = "CloudWatch log group name used by the Step Functions state machine."
  type        = string
  default     = "/aws/invoice-pipeline/dev/state-machine"
}

variable "tags" {
  description = "Additional tags applied to all resources."
  type        = map(string)
  default     = {}
}
