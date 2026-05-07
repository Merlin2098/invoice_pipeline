variable "bucket_name" {
  description = "Globally unique S3 bucket name."
  type        = string
}

variable "force_destroy" {
  description = "Allow bucket deletion even when objects remain. Intended for dev-only usage."
  type        = bool
  default     = false
}

variable "sse_algorithm" {
  description = "Default server-side encryption algorithm."
  type        = string
  default     = "AES256"
}

variable "policy_json" {
  description = "Optional bucket policy JSON document."
  type        = string
  default     = null
  nullable    = true
}

variable "create_object_prefixes" {
  description = "Optional list of S3 prefixes to materialize as zero-byte markers."
  type        = list(string)
  default     = []
}

variable "lifecycle_rules" {
  description = "Optional lifecycle rule placeholders keyed by prefix."
  type = list(object({
    id              = string
    prefix          = string
    expiration_days = number
  }))
  default = []
}

variable "tags" {
  description = "Tags applied to all bucket resources."
  type        = map(string)
}
