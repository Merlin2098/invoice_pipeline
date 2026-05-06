variable "state_machine_name" {
  description = "Step Functions state machine name."
  type        = string
}

variable "definition" {
  description = "Amazon States Language definition for the state machine."
  type        = string
}

variable "log_group_name" {
  description = "CloudWatch log group name for Step Functions execution logs."
  type        = string
}

variable "log_retention_in_days" {
  description = "Retention period for the Step Functions log group."
  type        = number
  default     = 30
}

variable "type" {
  description = "State machine type."
  type        = string
  default     = "STANDARD"
}

variable "logging_level" {
  description = "Logging level for Step Functions executions."
  type        = string
  default     = "ALL"
}

variable "include_execution_data" {
  description = "Include execution input and output in Step Functions logs."
  type        = bool
  default     = true
}

variable "additional_inline_policies" {
  description = "Additional inline policies keyed by policy name."
  type        = map(string)
  default     = {}
}

variable "managed_policy_arns" {
  description = "Managed policies to attach to the Step Functions role."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags applied to the state machine, role, and log group."
  type        = map(string)
}
