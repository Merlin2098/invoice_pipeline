output "state_bucket_name" {
  description = "Name of the Terraform state S3 bucket."
  value       = aws_s3_bucket.tfstate.bucket
}

output "state_bucket_arn" {
  description = "ARN of the Terraform state S3 bucket."
  value       = aws_s3_bucket.tfstate.arn
}

output "aws_account_id" {
  description = "AWS account ID where the bucket was created."
  value       = data.aws_caller_identity.current.account_id
}

output "backend_tf_snippet" {
  description = "Ready-to-paste backend block for infra/envs/dev/backend.tf."
  value       = <<-EOT
    terraform {
      backend "s3" {
        bucket       = "${aws_s3_bucket.tfstate.bucket}"
        key          = "invoice-pipeline/${var.environment}/terraform.tfstate"
        region       = "${var.aws_region}"
        use_lockfile = true
        encrypt      = true
      }
    }
  EOT
}
