output "lambda_arn" {
  description = "Lambda function ARN."
  value       = aws_lambda_function.this.arn
}

output "lambda_name" {
  description = "Lambda function name."
  value       = aws_lambda_function.this.function_name
}

output "invoke_arn" {
  description = "Lambda invoke ARN."
  value       = aws_lambda_function.this.invoke_arn
}
