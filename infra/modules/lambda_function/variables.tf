variable "function_name" {
  description = "Lambda function name."
  type        = string
}

variable "role_arn" {
  description = "IAM role ARN assumed by the Lambda function."
  type        = string
}

variable "s3_bucket" {
  description = "S3 bucket containing the deployment package."
  type        = string
}

variable "s3_key" {
  description = "S3 object key of the deployment package."
  type        = string
}

variable "runtime" {
  description = "Lambda runtime."
  type        = string
}

variable "handler" {
  description = "Lambda handler."
  type        = string
}

variable "timeout" {
  description = "Lambda timeout in seconds."
  type        = number
  default     = 60
}

variable "memory_size" {
  description = "Lambda memory size in MB."
  type        = number
  default     = 256
}

variable "publish" {
  description = "Publish a new version on update."
  type        = bool
  default     = false
}

variable "layers" {
  description = "Optional list of Lambda layer ARNs."
  type        = list(string)
  default     = []
}

variable "architectures" {
  description = "Instruction set architecture for the function."
  type        = list(string)
  default     = ["x86_64"]
}

variable "environment_variables" {
  description = "Environment variables passed to the function."
  type        = map(string)
  default     = {}
}

variable "source_code_hash" {
  description = "Base64-encoded SHA256 hash of the deployment package. Forces Lambda update when the ZIP changes."
  type        = string
  default     = null
  nullable    = true
}

variable "log_group_name" {
  description = "Optional externally managed log group name to depend on before creating the function."
  type        = string
  default     = null
  nullable    = true
}

variable "tags" {
  description = "Tags applied to the Lambda function."
  type        = map(string)
}
