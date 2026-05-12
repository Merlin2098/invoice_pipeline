output "queue_arn" {
  description = "FIFO queue ARN."
  value       = aws_sqs_queue.this.arn
}

output "queue_url" {
  description = "FIFO queue URL."
  value       = aws_sqs_queue.this.url
}

output "queue_name" {
  description = "FIFO queue name (includes .fifo suffix)."
  value       = aws_sqs_queue.this.name
}

output "dlq_arn" {
  description = "Dead letter queue ARN."
  value       = aws_sqs_queue.dlq.arn
}

output "dlq_url" {
  description = "Dead letter queue URL."
  value       = aws_sqs_queue.dlq.url
}
