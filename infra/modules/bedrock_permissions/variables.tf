variable "name" {
  description = "IAM policy name."
  type        = string
}

variable "aws_region" {
  description = "AWS region used to build the default Bedrock model ARN."
  type        = string
}

variable "model_id" {
  description = "Bedrock model identifier."
  type        = string
}

variable "model_arn_override" {
  description = "Optional explicit Bedrock model ARN for custom or provisioned models."
  type        = string
  default     = null
  nullable    = true
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
