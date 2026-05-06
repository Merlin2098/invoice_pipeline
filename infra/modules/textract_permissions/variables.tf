variable "name" {
  description = "IAM policy name."
  type        = string
}

variable "data_lake_bucket_arn" {
  description = "Data lake bucket ARN."
  type        = string
}

variable "raw_prefix" {
  description = "Raw S3 prefix inside the data lake bucket."
  type        = string
}

variable "bronze_prefix" {
  description = "Bronze S3 prefix inside the data lake bucket."
  type        = string
}

variable "attach_to_role_names" {
  description = "Optional list of IAM role names that should receive this managed policy."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags applied to the managed policy."
  type        = map(string)
}
