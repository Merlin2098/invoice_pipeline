variable "name" {
  description = "CloudWatch log group name."
  type        = string
}

variable "retention_in_days" {
  description = "Retention period for log events."
  type        = number
  default     = 30
}

variable "tags" {
  description = "Tags applied to the log group."
  type        = map(string)
}
