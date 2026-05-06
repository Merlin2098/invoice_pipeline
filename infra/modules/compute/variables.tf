variable "name_prefix" {
  type = string
}

variable "artifact_bucket_name" {
  type = string
}

variable "artifact_bucket_arn" {
  type = string
}

variable "data_lake_bucket_name" {
  type = string
}

variable "data_lake_bucket_arn" {
  type = string
}

variable "lambda_package_s3_key" {
  type = string
}

variable "normalize_script_s3_key" {
  type = string
}

variable "consolidate_script_s3_key" {
  type = string
}

variable "bedrock_model_id" {
  type = string
}

variable "cloudwatch_namespace" {
  type = string
}

variable "tags" {
  type = map(string)
}
