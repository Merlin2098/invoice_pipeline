variable "account_id" {
  type = string
}

variable "name_prefix" {
  type = string
}

variable "artifact_bucket_suffix" {
  type = string
}

variable "data_lake_bucket_suffix" {
  type = string
}

variable "raw_prefix" {
  type = string
}

variable "bronze_prefix" {
  type = string
}

variable "silver_valid_prefix" {
  type = string
}

variable "silver_rejected_prefix" {
  type = string
}

variable "gold_prefix" {
  type = string
}

variable "metrics_prefix" {
  type = string
}

variable "tags" {
  type = map(string)
}

