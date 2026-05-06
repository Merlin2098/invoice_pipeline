resource "aws_lambda_permission" "allow_s3_invoke" {
  statement_id  = "${var.statement_id_prefix}-s3"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_name
  principal     = "s3.amazonaws.com"
  source_arn    = var.bucket_arn
}

resource "aws_s3_bucket_notification" "this" {
  bucket = var.bucket_id

  lambda_function {
    lambda_function_arn = var.lambda_arn
    events              = var.events
    filter_prefix       = var.filter_prefix
    filter_suffix       = var.filter_suffix
  }

  depends_on = [aws_lambda_permission.allow_s3_invoke]
}
