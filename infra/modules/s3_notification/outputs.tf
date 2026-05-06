output "bucket_id" {
  description = "Bucket ID configured with notifications."
  value       = aws_s3_bucket_notification.this.bucket
}
