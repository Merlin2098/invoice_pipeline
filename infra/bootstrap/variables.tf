variable "project_name" {
  description = "Project name used in bucket name construction."
  type        = string
  default     = "invoice-pipeline"
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region where the state bucket is created."
  type        = string
  default     = "us-east-1"
}

variable "state_bucket_name_override" {
  description = "Optional explicit bucket name. Defaults to <project>-<env>-tfstate-<account_id>."
  type        = string
  default     = null
  nullable    = true
}
