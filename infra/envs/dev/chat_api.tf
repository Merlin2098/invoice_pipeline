locals {
  chat_lambda_name = "${local.name_prefix}-chat"
}

# ──────────────────────────────────────────────────────────────
# IAM policy documents
# ──────────────────────────────────────────────────────────────

data "aws_iam_policy_document" "chat_athena" {
  statement {
    sid = "RunAthenaQueries"
    actions = [
      "athena:StartQueryExecution",
      "athena:GetQueryExecution",
      "athena:GetQueryResults",
      "athena:StopQueryExecution",
    ]
    resources = [
      "arn:aws:athena:${var.aws_region}:${data.aws_caller_identity.current.account_id}:workgroup/${local.athena_workgroup_name}",
    ]
  }
}

data "aws_iam_policy_document" "chat_glue" {
  statement {
    sid = "ReadGlueCatalog"
    actions = [
      "glue:GetTable",
      "glue:GetTables",
      "glue:GetPartitions",
      "glue:GetDatabase",
    ]
    resources = [
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:database/${local.analytics_database_name}",
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${local.analytics_database_name}/*",
    ]
  }
}

data "aws_iam_policy_document" "chat_s3" {
  statement {
    sid     = "ReadGoldData"
    actions = ["s3:GetObject"]
    resources = [
      "${module.data_lake_bucket.bucket_arn}/${local.gold_prefix}/*",
    ]
  }

  statement {
    sid = "ReadWriteAthenaResults"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:GetBucketLocation",
    ]
    resources = [
      "${module.data_lake_bucket.bucket_arn}",
      "${module.data_lake_bucket.bucket_arn}/athena-results/*",
    ]
  }

  statement {
    sid     = "ListGoldAndResults"
    actions = ["s3:ListBucket"]
    resources = [module.data_lake_bucket.bucket_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "${local.gold_prefix}/",
        "${local.gold_prefix}/*",
        "athena-results/",
        "athena-results/*",
      ]
    }
  }
}

data "aws_iam_policy_document" "chat_logging" {
  statement {
    sid = "WriteChatLogs"
    actions = [
      "logs:CreateLogStream",
      "logs:DescribeLogStreams",
      "logs:PutLogEvents",
    ]
    resources = ["${module.chat_lambda_log_group.arn}:*"]
  }
}

# ──────────────────────────────────────────────────────────────
# CloudWatch log group
# ──────────────────────────────────────────────────────────────

module "chat_lambda_log_group" {
  source = "../../modules/cloudwatch_log_group"

  name              = "/aws/lambda/${local.chat_lambda_name}"
  retention_in_days = var.lambda_log_retention_in_days
  tags              = local.common_tags
}

# ──────────────────────────────────────────────────────────────
# IAM role
# ──────────────────────────────────────────────────────────────

module "chat_lambda_role" {
  source = "../../modules/iam_role"

  name             = "${local.name_prefix}-chat-role"
  trusted_services = ["lambda.amazonaws.com"]
  inline_policies = {
    logging = data.aws_iam_policy_document.chat_logging.json
    athena  = data.aws_iam_policy_document.chat_athena.json
    glue    = data.aws_iam_policy_document.chat_glue.json
    s3      = data.aws_iam_policy_document.chat_s3.json
  }
  tags = local.common_tags
}

module "chat_bedrock_permissions" {
  source = "../../modules/bedrock_permissions"

  name       = "${local.name_prefix}-chat-bedrock"
  aws_region = var.aws_region
  account_id = data.aws_caller_identity.current.account_id
  model_id   = var.bedrock_model_id
  attach_to_role_names = [module.chat_lambda_role.role_name]
  tags       = local.common_tags
}

# ──────────────────────────────────────────────────────────────
# Lambda function (slim chat bundle — no pandas/pyarrow)
# ──────────────────────────────────────────────────────────────

module "chat_lambda" {
  source = "../../modules/lambda_function"

  function_name    = local.chat_lambda_name
  role_arn         = module.chat_lambda_role.role_arn
  s3_bucket        = module.artifact_bucket.bucket_name
  s3_key           = var.chat_lambda_package_s3_key
  source_code_hash = filebase64sha256("${path.root}/../../../artifacts/lambda/chat_bundle.zip")
  runtime          = var.lambda_runtime
  handler          = "src.aws.lambda_handlers.control_plane.chat"
  timeout          = var.chat_lambda_timeout_seconds
  memory_size      = var.lambda_memory_size
  log_group_name   = module.chat_lambda_log_group.name
  environment_variables = {
    DATA_LAKE_BUCKET  = module.data_lake_bucket.bucket_name
    BEDROCK_MODEL_ID  = var.bedrock_model_id
    GLUE_DATABASE     = local.analytics_database_name
    ATHENA_WORKGROUP  = local.athena_workgroup_name
    AWS_REGION        = var.aws_region
  }
  tags = local.common_tags
}

# ──────────────────────────────────────────────────────────────
# API Gateway wiring (reuses the HTTP API from web_api.tf)
# ──────────────────────────────────────────────────────────────

resource "aws_lambda_permission" "chat_api_gw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = module.chat_lambda.lambda_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.web_api.execution_arn}/*/*"
}

resource "aws_apigatewayv2_integration" "chat" {
  api_id                 = aws_apigatewayv2_api.web_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = module.chat_lambda.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "post_chat" {
  api_id    = aws_apigatewayv2_api.web_api.id
  route_key = "POST /chat"
  target    = "integrations/${aws_apigatewayv2_integration.chat.id}"
}
