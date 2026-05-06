variable "name" {
  description = "IAM role name."
  type        = string
}

variable "trusted_services" {
  description = "AWS service principals allowed to assume the role."
  type        = list(string)
}

variable "inline_policies" {
  description = "Map of inline policy name to JSON policy document."
  type        = map(string)
  default     = {}
}

variable "managed_policy_arns" {
  description = "Managed policy ARNs to attach to the role."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags applied to the role."
  type        = map(string)
}
