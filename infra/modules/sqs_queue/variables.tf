variable "name" {
  description = "Base name. Main queue gets .fifo suffix; DLQ gets -dlq suffix."
  type        = string
}

variable "max_receive_count" {
  description = "Failures before a message moves to the DLQ."
  type        = number
  default     = 3
}

variable "visibility_timeout_seconds" {
  description = "Seconds a received message stays invisible. Must be >= 6x the consumer Lambda timeout."
  type        = number
  default     = 360
}

variable "message_retention_seconds" {
  description = "Seconds SQS retains undelivered messages in the main queue."
  type        = number
  default     = 86400
}

variable "dlq_message_retention_seconds" {
  description = "Seconds the DLQ retains messages."
  type        = number
  default     = 1209600
}

variable "tags" {
  description = "Tags applied to both queues. Must include Project=invoice-pipeline to be tracked by the monthly AWS Budget cost filter."
  type        = map(string)
}
