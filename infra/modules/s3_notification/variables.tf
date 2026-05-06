variable "bucket_id" {
  description = "S3 bucket ID where notifications are configured."
  type        = string
}

variable "bucket_arn" {
  description = "S3 bucket ARN used in Lambda invoke permission."
  type        = string
}

variable "lambda_arn" {
  description = "Lambda function ARN to invoke."
  type        = string
}

variable "lambda_name" {
  description = "Lambda function name used for invoke permission."
  type        = string
}

variable "events" {
  description = "List of S3 events that trigger the Lambda function."
  type        = list(string)
  default     = ["s3:ObjectCreated:*"]
}

variable "filter_prefix" {
  description = "Optional S3 key prefix filter."
  type        = string
  default     = null
  nullable    = true
}

variable "filter_suffix" {
  description = "Optional S3 key suffix filter."
  type        = string
  default     = null
  nullable    = true
}

variable "statement_id_prefix" {
  description = "Prefix used for the Lambda permission statement ID."
  type        = string
  default     = "allow"
}
