data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "lambda_logging" {
  statement {
    sid = "WriteFunctionLogs"
    actions = [
      "logs:CreateLogStream",
      "logs:DescribeLogStreams",
      "logs:PutLogEvents",
    ]
    resources = ["${module.raw_ingestion_log_group.arn}:*"]
  }
}

data "aws_iam_policy_document" "lambda_data_lake_access" {
  statement {
    sid       = "ReadRawObjects"
    actions   = ["s3:GetObject"]
    resources = ["${module.data_lake_bucket.bucket_arn}/${local.raw_prefix}/*"]
  }

  statement {
    sid       = "ListRawPrefix"
    actions   = ["s3:ListBucket"]
    resources = [module.data_lake_bucket.bucket_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        local.raw_prefix,
        "${local.raw_prefix}/*",
      ]
    }
  }
}

data "aws_iam_policy_document" "step_function_lambda_invoke" {
  statement {
    sid     = "InvokeFoundationLambda"
    actions = ["lambda:InvokeFunction"]
    resources = [
      module.raw_ingestion_lambda.lambda_arn,
      "${module.raw_ingestion_lambda.lambda_arn}:*",
    ]
  }
}

locals {
  name_prefix = lower(replace("${var.project_name}-${var.environment}", "_", "-"))

  artifact_bucket_name = coalesce(
    var.artifact_bucket_name_override,
    "${local.name_prefix}-${data.aws_caller_identity.current.account_id}-${var.artifact_bucket_suffix}"
  )
  data_lake_bucket_name = coalesce(
    var.data_lake_bucket_name_override,
    "${local.name_prefix}-${data.aws_caller_identity.current.account_id}-${var.data_lake_bucket_suffix}"
  )

  raw_prefix             = trim(var.raw_prefix, "/")
  bronze_prefix          = trim(var.bronze_prefix, "/")
  silver_valid_prefix    = trim(var.silver_valid_prefix, "/")
  silver_rejected_prefix = trim(var.silver_rejected_prefix, "/")
  gold_prefix            = trim(var.gold_prefix, "/")
  errors_prefix          = trim(var.errors_prefix, "/")

  common_tags = merge(
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
      Owner       = var.owner
      Platform    = "document-intelligence"
    },
    var.tags
  )

  data_lake_prefix_markers = [
    "${local.raw_prefix}/",
    "${local.bronze_prefix}/",
    "${local.silver_valid_prefix}/",
    "${local.silver_rejected_prefix}/",
    "${local.gold_prefix}/",
    "${local.errors_prefix}/",
  ]
}

module "artifact_bucket" {
  source = "../../modules/s3_bucket"

  bucket_name   = local.artifact_bucket_name
  force_destroy = var.force_destroy
  tags          = local.common_tags
}

module "data_lake_bucket" {
  source = "../../modules/s3_bucket"

  bucket_name            = local.data_lake_bucket_name
  force_destroy          = var.force_destroy
  create_object_prefixes = local.data_lake_prefix_markers
  tags                   = local.common_tags
}

module "raw_ingestion_log_group" {
  source = "../../modules/cloudwatch_log_group"

  name              = "/aws/lambda/${local.name_prefix}-raw-ingestion"
  retention_in_days = var.lambda_log_retention_in_days
  tags              = local.common_tags
}

module "raw_ingestion_role" {
  source = "../../modules/iam_role"

  name             = "${local.name_prefix}-raw-ingestion-role"
  trusted_services = ["lambda.amazonaws.com"]
  inline_policies = {
    logging        = data.aws_iam_policy_document.lambda_logging.json
    data_lake_read = data.aws_iam_policy_document.lambda_data_lake_access.json
  }
  tags = local.common_tags
}

module "raw_ingestion_lambda" {
  source = "../../modules/lambda_function"

  function_name  = "${local.name_prefix}-raw-ingestion"
  role_arn       = module.raw_ingestion_role.role_arn
  s3_bucket      = module.artifact_bucket.bucket_name
  s3_key         = var.lambda_package_s3_key
  runtime        = var.lambda_runtime
  handler        = var.lambda_handler
  timeout        = var.lambda_timeout_seconds
  memory_size    = var.lambda_memory_size
  log_group_name = module.raw_ingestion_log_group.name
  environment_variables = {
    DATA_LAKE_BUCKET       = module.data_lake_bucket.bucket_name
    RAW_PREFIX             = local.raw_prefix
    BRONZE_PREFIX          = local.bronze_prefix
    SILVER_VALID_PREFIX    = local.silver_valid_prefix
    SILVER_REJECTED_PREFIX = local.silver_rejected_prefix
    GOLD_PREFIX            = local.gold_prefix
    ERRORS_PREFIX          = local.errors_prefix
    TRACEABILITY_MODE      = "run_id_ready"
  }
  tags = local.common_tags
}

module "raw_upload_notification" {
  source = "../../modules/s3_notification"

  bucket_id           = module.data_lake_bucket.bucket_id
  bucket_arn          = module.data_lake_bucket.bucket_arn
  lambda_arn          = module.raw_ingestion_lambda.lambda_arn
  lambda_name         = module.raw_ingestion_lambda.lambda_name
  filter_prefix       = "${local.raw_prefix}/"
  filter_suffix       = var.raw_trigger_suffix
  statement_id_prefix = "${local.name_prefix}-raw-upload"
}

module "invoice_pipeline_state_machine" {
  source = "../../modules/step_function"

  state_machine_name = "${local.name_prefix}-foundation"
  definition = templatefile("${path.module}/state_machine.asl.json", {
    raw_ingestion_lambda_arn = module.raw_ingestion_lambda.lambda_arn
  })
  log_group_name        = "/aws/vendedlogs/states/${local.name_prefix}-foundation"
  log_retention_in_days = var.step_function_log_retention_in_days
  additional_inline_policies = {
    lambda_invoke = data.aws_iam_policy_document.step_function_lambda_invoke.json
  }
  tags = local.common_tags
}

module "textract_permissions" {
  source = "../../modules/textract_permissions"

  name                 = "${local.name_prefix}-textract"
  data_lake_bucket_arn = module.data_lake_bucket.bucket_arn
  raw_prefix           = local.raw_prefix
  bronze_prefix        = local.bronze_prefix
  attach_to_role_names = [module.invoice_pipeline_state_machine.role_name]
  tags                 = local.common_tags
}

module "bedrock_permissions" {
  source = "../../modules/bedrock_permissions"

  name                 = "${local.name_prefix}-bedrock"
  aws_region           = var.aws_region
  model_id             = var.bedrock_model_id
  attach_to_role_names = [module.invoice_pipeline_state_machine.role_name]
  tags                 = local.common_tags
}
