resource "terraform_data" "log_group_dependency" {
  input = var.log_group_name
}

resource "aws_lambda_function" "this" {
  function_name    = var.function_name
  role             = var.role_arn
  s3_bucket        = var.s3_bucket
  s3_key           = var.s3_key
  source_code_hash = var.source_code_hash
  runtime          = var.runtime
  handler          = var.handler
  timeout          = var.timeout
  memory_size      = var.memory_size
  publish          = var.publish
  layers           = var.layers
  architectures    = var.architectures
  tags             = var.tags

  dynamic "environment" {
    for_each = length(var.environment_variables) == 0 ? [] : [var.environment_variables]

    content {
      variables = environment.value
    }
  }

  depends_on = [terraform_data.log_group_dependency]
}
