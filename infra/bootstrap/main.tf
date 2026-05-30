terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

locals {
  bucket_name = coalesce(
    var.state_bucket_name_override,
    "${var.project_name}-${var.environment}-tfstate-${data.aws_caller_identity.current.account_id}"
  )

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform-bootstrap"
    Purpose     = "terraform-remote-state"
  }
}

resource "aws_s3_bucket" "tfstate" {
  bucket        = local.bucket_name
  force_destroy = false

  tags = local.tags
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
