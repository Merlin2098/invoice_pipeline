locals {
  artifact_bucket_name  = "${var.name_prefix}-${var.account_id}-${var.artifact_bucket_suffix}"
  data_lake_bucket_name = "${var.name_prefix}-${var.account_id}-${var.data_lake_bucket_suffix}"
}

resource "aws_s3_bucket" "artifact" {
  bucket = local.artifact_bucket_name
  tags   = var.tags
}

resource "aws_s3_bucket" "data_lake" {
  bucket = local.data_lake_bucket_name
  tags   = merge(var.tags, { DataLake = "true" })
}

resource "aws_s3_bucket_versioning" "artifact" {
  bucket = aws_s3_bucket.artifact.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_versioning" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifact" {
  bucket = aws_s3_bucket.artifact.bucket

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.bucket

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "artifact" {
  bucket = aws_s3_bucket.artifact.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_object" "prefix_markers" {
  for_each = toset([
    "${trim(var.raw_prefix, "/")}/",
    "${trim(var.bronze_prefix, "/")}/",
    "${trim(var.silver_valid_prefix, "/")}/",
    "${trim(var.silver_rejected_prefix, "/")}/",
    "${trim(var.gold_prefix, "/")}/",
    "${trim(var.metrics_prefix, "/")}/",
  ])

  bucket  = aws_s3_bucket.data_lake.id
  key     = each.value
  content = ""
}

