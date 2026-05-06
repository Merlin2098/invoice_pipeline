variable "name_prefix" {
  type = string
}

variable "data_lake_bucket_name" {
  type = string
}

variable "data_lake_bucket_arn" {
  type = string
}

variable "raw_prefix" {
  type = string
}

variable "bronze_prefix" {
  type = string
}

variable "silver_valid_prefix" {
  type = string
}

variable "silver_rejected_prefix" {
  type = string
}

variable "gold_prefix" {
  type = string
}

variable "metrics_prefix" {
  type = string
}

variable "prevalidation_lambda_arn" {
  type = string
}

variable "publish_metrics_lambda_arn" {
  type = string
}

variable "normalize_job_name" {
  type = string
}

variable "consolidate_job_name" {
  type = string
}

variable "bedrock_model_id" {
  type = string
}

variable "state_machine_log_group_name" {
  type = string
}

variable "tags" {
  type = map(string)
}

