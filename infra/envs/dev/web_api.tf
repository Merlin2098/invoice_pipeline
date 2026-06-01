locals {
  web_api_name               = "${local.name_prefix}-web-api"
  upload_lambda_name         = "${local.name_prefix}-upload"
  invoice_status_lambda_name = "${local.name_prefix}-invoice-status"
  list_invoices_lambda_name  = "${local.name_prefix}-list-invoices"
  status_prefix              = "status"
}

# ──────────────────────────────────────────────────────────────
# IAM policy documents
# ──────────────────────────────────────────────────────────────

data "aws_iam_policy_document" "upload_lambda_s3" {
  statement {
    sid     = "PresignRawUploads"
    actions = ["s3:PutObject"]
    resources = [
      "${module.data_lake_bucket.bucket_arn}/${local.raw_prefix}/*",
    ]
  }

  statement {
    sid     = "WriteUploadedStatus"
    actions = ["s3:PutObject"]
    resources = [
      "${module.data_lake_bucket.bucket_arn}/${local.status_prefix}/*",
    ]
  }
}

data "aws_iam_policy_document" "status_lambda_s3" {
  statement {
    sid     = "ReadStatusObjects"
    actions = ["s3:GetObject"]
    resources = [
      "${module.data_lake_bucket.bucket_arn}/${local.status_prefix}/*",
    ]
  }

  statement {
    sid       = "ListStatusPrefix"
    actions   = ["s3:ListBucket"]
    resources = [module.data_lake_bucket.bucket_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${local.status_prefix}/", "${local.status_prefix}/*"]
    }
  }
}

data "aws_iam_policy_document" "pipeline_status_write" {
  statement {
    sid     = "WritePipelineStatus"
    actions = ["s3:PutObject"]
    resources = [
      "${module.data_lake_bucket.bucket_arn}/${local.status_prefix}/*",
    ]
  }
}

# ──────────────────────────────────────────────────────────────
# CloudWatch log groups
# ──────────────────────────────────────────────────────────────

module "upload_lambda_log_group" {
  source = "../../modules/cloudwatch_log_group"

  name              = "/aws/lambda/${local.upload_lambda_name}"
  retention_in_days = var.lambda_log_retention_in_days
  tags              = local.common_tags
}

module "invoice_status_lambda_log_group" {
  source = "../../modules/cloudwatch_log_group"

  name              = "/aws/lambda/${local.invoice_status_lambda_name}"
  retention_in_days = var.lambda_log_retention_in_days
  tags              = local.common_tags
}

module "list_invoices_lambda_log_group" {
  source = "../../modules/cloudwatch_log_group"

  name              = "/aws/lambda/${local.list_invoices_lambda_name}"
  retention_in_days = var.lambda_log_retention_in_days
  tags              = local.common_tags
}

resource "aws_cloudwatch_log_group" "web_api_access" {
  name              = "/aws/apigateway/${local.web_api_name}"
  retention_in_days = var.lambda_log_retention_in_days
  tags              = local.common_tags
}

# ──────────────────────────────────────────────────────────────
# IAM roles
# ──────────────────────────────────────────────────────────────

data "aws_iam_policy_document" "web_api_logging" {
  statement {
    sid = "WriteFunctionLogs"
    actions = [
      "logs:CreateLogStream",
      "logs:DescribeLogStreams",
      "logs:PutLogEvents",
    ]
    resources = [
      "${module.upload_lambda_log_group.arn}:*",
      "${module.invoice_status_lambda_log_group.arn}:*",
      "${module.list_invoices_lambda_log_group.arn}:*",
    ]
  }
}

module "upload_lambda_role" {
  source = "../../modules/iam_role"

  name             = "${local.name_prefix}-upload-role"
  trusted_services = ["lambda.amazonaws.com"]
  inline_policies = {
    logging    = data.aws_iam_policy_document.web_api_logging.json
    s3_presign = data.aws_iam_policy_document.upload_lambda_s3.json
  }
  tags = local.common_tags
}

module "invoice_status_lambda_role" {
  source = "../../modules/iam_role"

  name             = "${local.name_prefix}-invoice-status-role"
  trusted_services = ["lambda.amazonaws.com"]
  inline_policies = {
    logging   = data.aws_iam_policy_document.web_api_logging.json
    s3_status = data.aws_iam_policy_document.status_lambda_s3.json
  }
  tags = local.common_tags
}

module "list_invoices_lambda_role" {
  source = "../../modules/iam_role"

  name             = "${local.name_prefix}-list-invoices-role"
  trusted_services = ["lambda.amazonaws.com"]
  inline_policies = {
    logging   = data.aws_iam_policy_document.web_api_logging.json
    s3_status = data.aws_iam_policy_document.status_lambda_s3.json
  }
  tags = local.common_tags
}

# Attach status-write permission to existing pipeline roles
resource "aws_iam_role_policy" "validate_input_status_write" {
  name   = "status-write"
  role   = module.validate_input_role.role_name
  policy = data.aws_iam_policy_document.pipeline_status_write.json
}

resource "aws_iam_role_policy" "enrich_llm_status_write" {
  name   = "status-write"
  role   = module.enrich_llm_role.role_name
  policy = data.aws_iam_policy_document.pipeline_status_write.json
}

# ──────────────────────────────────────────────────────────────
# Lambda functions
# ──────────────────────────────────────────────────────────────

module "upload_lambda" {
  source = "../../modules/lambda_function"

  function_name    = local.upload_lambda_name
  role_arn         = module.upload_lambda_role.role_arn
  s3_bucket        = module.artifact_bucket.bucket_name
  s3_key           = var.lambda_package_s3_key
  source_code_hash = filebase64sha256("${path.root}/../../../artifacts/lambda/control_plane_bundle.zip")
  runtime          = var.lambda_runtime
  handler          = "src.aws.lambda_handlers.control_plane.generate_upload_urls"
  timeout          = 30
  memory_size      = var.lambda_memory_size
  log_group_name   = module.upload_lambda_log_group.name
  environment_variables = {
    DATA_LAKE_BUCKET             = module.data_lake_bucket.bucket_name
    RAW_PREFIX                   = local.raw_prefix
    UPLOAD_ALLOWED_CONTENT_TYPES = "application/pdf,image/tiff,image/tif,application/octet-stream"
    UPLOAD_ALLOWED_EXTENSIONS    = ".pdf,.tif,.tiff"
  }
  tags = local.common_tags
}

module "invoice_status_lambda" {
  source = "../../modules/lambda_function"

  function_name    = local.invoice_status_lambda_name
  role_arn         = module.invoice_status_lambda_role.role_arn
  s3_bucket        = module.artifact_bucket.bucket_name
  s3_key           = var.lambda_package_s3_key
  source_code_hash = filebase64sha256("${path.root}/../../../artifacts/lambda/control_plane_bundle.zip")
  runtime          = var.lambda_runtime
  handler          = "src.aws.lambda_handlers.control_plane.get_invoice_status"
  timeout          = 15
  memory_size      = var.lambda_memory_size
  log_group_name   = module.invoice_status_lambda_log_group.name
  environment_variables = {
    DATA_LAKE_BUCKET = module.data_lake_bucket.bucket_name
  }
  tags = local.common_tags
}

module "list_invoices_lambda" {
  source = "../../modules/lambda_function"

  function_name    = local.list_invoices_lambda_name
  role_arn         = module.list_invoices_lambda_role.role_arn
  s3_bucket        = module.artifact_bucket.bucket_name
  s3_key           = var.lambda_package_s3_key
  source_code_hash = filebase64sha256("${path.root}/../../../artifacts/lambda/control_plane_bundle.zip")
  runtime          = var.lambda_runtime
  handler          = "src.aws.lambda_handlers.control_plane.list_invoices"
  timeout          = 15
  memory_size      = var.lambda_memory_size
  log_group_name   = module.list_invoices_lambda_log_group.name
  environment_variables = {
    DATA_LAKE_BUCKET = module.data_lake_bucket.bucket_name
  }
  tags = local.common_tags
}

# ──────────────────────────────────────────────────────────────
# API Gateway HTTP API v2
# ──────────────────────────────────────────────────────────────

resource "aws_apigatewayv2_api" "web_api" {
  name          = local.web_api_name
  protocol_type = "HTTP"
  description   = "Invoice pipeline web API — upload, status, and history endpoints."

  cors_configuration {
    allow_origins = var.web_api_cors_origins
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["Content-Type"]
    max_age       = 300
  }

  tags = local.common_tags
}

resource "aws_s3_bucket_cors_configuration" "data_lake_uploads" {
  bucket = module.data_lake_bucket.bucket_id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT", "GET", "HEAD"]
    allowed_origins = var.web_api_cors_origins
    expose_headers  = ["ETag"]
    max_age_seconds = 300
  }
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.web_api.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.web_api_access.arn
    format = jsonencode({
      requestId        = "$context.requestId"
      ip               = "$context.identity.sourceIp"
      requestTime      = "$context.requestTime"
      httpMethod       = "$context.httpMethod"
      routeKey         = "$context.routeKey"
      status           = "$context.status"
      protocol         = "$context.protocol"
      responseLength   = "$context.responseLength"
      integrationError = "$context.integrationErrorMessage"
    })
  }

  tags = local.common_tags
}

# Lambda permissions for API Gateway
resource "aws_lambda_permission" "upload_api_gw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = module.upload_lambda.lambda_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.web_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "invoice_status_api_gw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = module.invoice_status_lambda.lambda_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.web_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "list_invoices_api_gw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = module.list_invoices_lambda.lambda_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.web_api.execution_arn}/*/*"
}

# Lambda integrations
resource "aws_apigatewayv2_integration" "upload" {
  api_id                 = aws_apigatewayv2_api.web_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = module.upload_lambda.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "invoice_status" {
  api_id                 = aws_apigatewayv2_api.web_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = module.invoice_status_lambda.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "list_invoices" {
  api_id                 = aws_apigatewayv2_api.web_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = module.list_invoices_lambda.invoke_arn
  payload_format_version = "2.0"
}

# Routes
resource "aws_apigatewayv2_route" "post_uploads" {
  api_id    = aws_apigatewayv2_api.web_api.id
  route_key = "POST /uploads"
  target    = "integrations/${aws_apigatewayv2_integration.upload.id}"
}

resource "aws_apigatewayv2_route" "get_invoice_status" {
  api_id    = aws_apigatewayv2_api.web_api.id
  route_key = "GET /invoices/{invoice_id}/status"
  target    = "integrations/${aws_apigatewayv2_integration.invoice_status.id}"
}

resource "aws_apigatewayv2_route" "get_invoices" {
  api_id    = aws_apigatewayv2_api.web_api.id
  route_key = "GET /invoices"
  target    = "integrations/${aws_apigatewayv2_integration.list_invoices.id}"
}
