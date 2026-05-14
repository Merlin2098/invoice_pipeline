data "aws_caller_identity" "current" {}

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
  gold_manifest_prefix   = "gold/manifests"
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
    "${local.gold_manifest_prefix}/",
    "${local.errors_prefix}/",
    "athena-results/",
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

module "raw_dispatch_log_group" {
  source = "../../modules/cloudwatch_log_group"

  name              = "/aws/lambda/${local.name_prefix}-raw-dispatch"
  retention_in_days = var.lambda_log_retention_in_days
  tags              = local.common_tags
}

module "validate_input_log_group" {
  source = "../../modules/cloudwatch_log_group"

  name              = "/aws/lambda/${local.name_prefix}-validate-input"
  retention_in_days = var.lambda_log_retention_in_days
  tags              = local.common_tags
}

module "process_document_log_group" {
  source = "../../modules/cloudwatch_log_group"

  name              = "/aws/lambda/${local.name_prefix}-process-document"
  retention_in_days = var.lambda_log_retention_in_days
  tags              = local.common_tags
}

module "extract_ocr_log_group" {
  source = "../../modules/cloudwatch_log_group"

  name              = "/aws/lambda/${local.name_prefix}-extract-ocr"
  retention_in_days = var.lambda_log_retention_in_days
  tags              = local.common_tags
}

module "enrich_llm_log_group" {
  source = "../../modules/cloudwatch_log_group"

  name              = "/aws/lambda/${local.name_prefix}-enrich-llm"
  retention_in_days = var.lambda_log_retention_in_days
  tags              = local.common_tags
}

module "publish_metrics_log_group" {
  source = "../../modules/cloudwatch_log_group"

  name              = "/aws/lambda/${local.name_prefix}-publish-metrics"
  retention_in_days = var.lambda_log_retention_in_days
  tags              = local.common_tags
}

module "consolidate_gold_log_group" {
  source = "../../modules/cloudwatch_log_group"

  name              = "/aws/lambda/${local.name_prefix}-consolidate-gold"
  retention_in_days = var.lambda_log_retention_in_days
  tags              = local.common_tags
}

data "aws_iam_policy_document" "lambda_logging" {
  statement {
    sid = "WriteFunctionLogs"
    actions = [
      "logs:CreateLogStream",
      "logs:DescribeLogStreams",
      "logs:PutLogEvents",
    ]
    resources = [
      "${module.raw_dispatch_log_group.arn}:*",
      "${module.validate_input_log_group.arn}:*",
      "${module.process_document_log_group.arn}:*",
      "${module.extract_ocr_log_group.arn}:*",
      "${module.enrich_llm_log_group.arn}:*",
      "${module.publish_metrics_log_group.arn}:*",
      "${module.consolidate_gold_log_group.arn}:*",
    ]
  }
}

data "aws_iam_policy_document" "dispatcher_start_execution" {
  statement {
    sid     = "StartPipelineExecution"
    actions = ["states:StartExecution"]
    resources = [
      module.invoice_pipeline_state_machine.state_machine_arn,
    ]
  }
}

data "aws_iam_policy_document" "raw_dispatch_sqs_consume" {
  statement {
    sid = "ConsumeSqsMessages"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ChangeMessageVisibility",
    ]
    resources = [module.raw_ingestion_queue.queue_arn]
  }
}

data "aws_iam_policy_document" "s3_to_sqs_send" {
  statement {
    sid       = "AllowS3SendMessage"
    actions   = ["sqs:SendMessage"]
    resources = [module.raw_ingestion_queue.queue_arn]

    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = [module.data_lake_bucket.bucket_arn]
    }
  }
}

data "aws_iam_policy_document" "process_document_data_lake_access" {
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

  statement {
    sid     = "CheckSilverIdempotency"
    actions = ["s3:GetObject"]
    resources = [
      "${module.data_lake_bucket.bucket_arn}/${local.silver_valid_prefix}/*",
    ]
  }

  statement {
    sid       = "ListSilverValidPrefix"
    actions   = ["s3:ListBucket"]
    resources = [module.data_lake_bucket.bucket_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        local.silver_valid_prefix,
        "${local.silver_valid_prefix}/*",
      ]
    }
  }

  statement {
    sid = "WritePipelineOutputs"
    actions = [
      "s3:PutObject",
    ]
    resources = [
      "${module.data_lake_bucket.bucket_arn}/${local.bronze_prefix}/*",
      "${module.data_lake_bucket.bucket_arn}/${local.silver_valid_prefix}/*",
      "${module.data_lake_bucket.bucket_arn}/${local.silver_rejected_prefix}/*",
      "${module.data_lake_bucket.bucket_arn}/${local.errors_prefix}/*",
    ]
  }
}

data "aws_iam_policy_document" "extract_ocr_data_lake_access" {
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

  statement {
    sid       = "CheckSilverIdempotency"
    actions   = ["s3:GetObject"]
    resources = ["${module.data_lake_bucket.bucket_arn}/${local.silver_valid_prefix}/*"]
  }

  statement {
    sid       = "ListSilverValidPrefix"
    actions   = ["s3:ListBucket"]
    resources = [module.data_lake_bucket.bucket_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        local.silver_valid_prefix,
        "${local.silver_valid_prefix}/*",
      ]
    }
  }

  statement {
    sid       = "WriteBronzeObjects"
    actions   = ["s3:PutObject"]
    resources = ["${module.data_lake_bucket.bucket_arn}/${local.bronze_prefix}/*"]
  }
}

data "aws_iam_policy_document" "enrich_llm_data_lake_access" {
  statement {
    sid       = "ReadBronzeObjects"
    actions   = ["s3:GetObject"]
    resources = ["${module.data_lake_bucket.bucket_arn}/${local.bronze_prefix}/*"]
  }

  statement {
    sid       = "ListBronzePrefix"
    actions   = ["s3:ListBucket"]
    resources = [module.data_lake_bucket.bucket_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        local.bronze_prefix,
        "${local.bronze_prefix}/*",
      ]
    }
  }

  statement {
    sid = "WriteFinalOutputs"
    actions = [
      "s3:PutObject",
    ]
    resources = [
      "${module.data_lake_bucket.bucket_arn}/${local.silver_valid_prefix}/*",
      "${module.data_lake_bucket.bucket_arn}/${local.silver_rejected_prefix}/*",
      "${module.data_lake_bucket.bucket_arn}/${local.errors_prefix}/*",
    ]
  }
}

data "aws_iam_policy_document" "publish_metrics_cloudwatch" {
  statement {
    sid       = "PublishCustomMetrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
  }
}

data "aws_iam_policy_document" "consolidate_gold_data_lake_access" {
  statement {
    sid     = "ReadTerminalSilverOutputs"
    actions = ["s3:GetObject"]
    resources = [
      "${module.data_lake_bucket.bucket_arn}/${local.silver_valid_prefix}/*",
      "${module.data_lake_bucket.bucket_arn}/${local.silver_rejected_prefix}/*",
      "${module.data_lake_bucket.bucket_arn}/${local.errors_prefix}/*",
    ]
  }

  statement {
    sid       = "ListTerminalSilverPrefixes"
    actions   = ["s3:ListBucket"]
    resources = [module.data_lake_bucket.bucket_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        local.silver_valid_prefix,
        "${local.silver_valid_prefix}/*",
        local.silver_rejected_prefix,
        "${local.silver_rejected_prefix}/*",
        local.errors_prefix,
        "${local.errors_prefix}/*",
      ]
    }
  }

  statement {
    sid     = "WriteGoldOutputs"
    actions = ["s3:PutObject"]
    resources = [
      "${module.data_lake_bucket.bucket_arn}/${local.gold_prefix}/*",
      "${module.data_lake_bucket.bucket_arn}/${local.gold_manifest_prefix}/*",
    ]
  }
}

data "aws_iam_policy_document" "step_function_lambda_invoke" {
  statement {
    sid     = "InvokePipelineLambdas"
    actions = ["lambda:InvokeFunction"]
    resources = [
      module.validate_input_lambda.lambda_arn,
      "${module.validate_input_lambda.lambda_arn}:*",
      module.process_document_lambda.lambda_arn,
      "${module.process_document_lambda.lambda_arn}:*",
      module.extract_ocr_lambda.lambda_arn,
      "${module.extract_ocr_lambda.lambda_arn}:*",
      module.enrich_llm_lambda.lambda_arn,
      "${module.enrich_llm_lambda.lambda_arn}:*",
      module.publish_metrics_lambda.lambda_arn,
      "${module.publish_metrics_lambda.lambda_arn}:*",
    ]
  }
}

module "raw_ingestion_queue" {
  source = "../../modules/sqs_queue"

  name                       = "${local.name_prefix}-raw-ingestion"
  visibility_timeout_seconds = 6 * var.lambda_timeout_seconds
  tags                       = local.common_tags
}

resource "aws_sqs_queue_policy" "raw_ingestion" {
  queue_url = module.raw_ingestion_queue.queue_url
  policy    = data.aws_iam_policy_document.s3_to_sqs_send.json
}

module "invoice_pipeline_state_machine" {
  source = "../../modules/step_function"

  state_machine_name = "${local.name_prefix}-document-pipeline"
  definition = templatefile("${path.module}/state_machine.asl.json", {
    validate_input_lambda_arn   = module.validate_input_lambda.lambda_arn
    process_document_lambda_arn = module.process_document_lambda.lambda_arn
    extract_ocr_lambda_arn      = module.extract_ocr_lambda.lambda_arn
    enrich_llm_lambda_arn       = module.enrich_llm_lambda.lambda_arn
    publish_metrics_lambda_arn  = module.publish_metrics_lambda.lambda_arn
  })
  log_group_name        = "/aws/vendedlogs/states/${local.name_prefix}-document-pipeline"
  log_retention_in_days = var.step_function_log_retention_in_days
  additional_inline_policies = {
    lambda_invoke = data.aws_iam_policy_document.step_function_lambda_invoke.json
  }
  tags = local.common_tags
}

module "raw_dispatch_role" {
  source = "../../modules/iam_role"

  name             = "${local.name_prefix}-raw-dispatch-role"
  trusted_services = ["lambda.amazonaws.com"]
  inline_policies = {
    logging         = data.aws_iam_policy_document.lambda_logging.json
    start_execution = data.aws_iam_policy_document.dispatcher_start_execution.json
    sqs_consume     = data.aws_iam_policy_document.raw_dispatch_sqs_consume.json
  }
  tags = local.common_tags
}

module "validate_input_role" {
  source = "../../modules/iam_role"

  name             = "${local.name_prefix}-validate-input-role"
  trusted_services = ["lambda.amazonaws.com"]
  inline_policies = {
    logging = data.aws_iam_policy_document.lambda_logging.json
  }
  tags = local.common_tags
}

module "process_document_role" {
  source = "../../modules/iam_role"

  name             = "${local.name_prefix}-process-document-role"
  trusted_services = ["lambda.amazonaws.com"]
  inline_policies = {
    logging          = data.aws_iam_policy_document.lambda_logging.json
    data_lake_access = data.aws_iam_policy_document.process_document_data_lake_access.json
  }
  tags = local.common_tags
}

module "extract_ocr_role" {
  source = "../../modules/iam_role"

  name             = "${local.name_prefix}-extract-ocr-role"
  trusted_services = ["lambda.amazonaws.com"]
  inline_policies = {
    logging          = data.aws_iam_policy_document.lambda_logging.json
    data_lake_access = data.aws_iam_policy_document.extract_ocr_data_lake_access.json
  }
  tags = local.common_tags
}

module "enrich_llm_role" {
  source = "../../modules/iam_role"

  name             = "${local.name_prefix}-enrich-llm-role"
  trusted_services = ["lambda.amazonaws.com"]
  inline_policies = {
    logging          = data.aws_iam_policy_document.lambda_logging.json
    data_lake_access = data.aws_iam_policy_document.enrich_llm_data_lake_access.json
  }
  tags = local.common_tags
}

module "publish_metrics_role" {
  source = "../../modules/iam_role"

  name             = "${local.name_prefix}-publish-metrics-role"
  trusted_services = ["lambda.amazonaws.com"]
  inline_policies = {
    logging          = data.aws_iam_policy_document.lambda_logging.json
    cloudwatch_write = data.aws_iam_policy_document.publish_metrics_cloudwatch.json
  }
  tags = local.common_tags
}

module "consolidate_gold_role" {
  source = "../../modules/iam_role"

  name             = "${local.name_prefix}-consolidate-gold-role"
  trusted_services = ["lambda.amazonaws.com"]
  inline_policies = {
    logging          = data.aws_iam_policy_document.lambda_logging.json
    data_lake_access = data.aws_iam_policy_document.consolidate_gold_data_lake_access.json
  }
  tags = local.common_tags
}

module "raw_dispatch_lambda" {
  source = "../../modules/lambda_function"

  function_name    = "${local.name_prefix}-raw-dispatch"
  role_arn         = module.raw_dispatch_role.role_arn
  s3_bucket        = module.artifact_bucket.bucket_name
  s3_key           = var.lambda_package_s3_key
  source_code_hash = filebase64sha256("${path.root}/../../../artifacts/lambda/control_plane_bundle.zip")
  runtime          = var.lambda_runtime
  handler          = var.raw_dispatch_handler
  timeout          = var.lambda_timeout_seconds
  memory_size      = var.lambda_memory_size
  log_group_name   = module.raw_dispatch_log_group.name
  environment_variables = {
    DATA_LAKE_BUCKET  = module.data_lake_bucket.bucket_name
    STATE_MACHINE_ARN = module.invoice_pipeline_state_machine.state_machine_arn
    TRACEABILITY_MODE = "run_id_ready"
  }
  tags = local.common_tags
}

module "validate_input_lambda" {
  source = "../../modules/lambda_function"

  function_name    = "${local.name_prefix}-validate-input"
  role_arn         = module.validate_input_role.role_arn
  s3_bucket        = module.artifact_bucket.bucket_name
  s3_key           = var.lambda_package_s3_key
  source_code_hash = filebase64sha256("${path.root}/../../../artifacts/lambda/control_plane_bundle.zip")
  runtime          = var.lambda_runtime
  handler          = var.validate_input_handler
  timeout          = var.lambda_timeout_seconds
  memory_size      = var.lambda_memory_size
  log_group_name   = module.validate_input_log_group.name
  tags             = local.common_tags
}

module "process_document_lambda" {
  source = "../../modules/lambda_function"

  function_name    = "${local.name_prefix}-process-document"
  role_arn         = module.process_document_role.role_arn
  s3_bucket        = module.artifact_bucket.bucket_name
  s3_key           = var.lambda_package_s3_key
  source_code_hash = filebase64sha256("${path.root}/../../../artifacts/lambda/control_plane_bundle.zip")
  runtime          = var.lambda_runtime
  handler          = var.process_document_handler
  timeout          = var.lambda_timeout_seconds
  memory_size      = var.lambda_memory_size
  log_group_name   = module.process_document_log_group.name
  environment_variables = {
    DATA_LAKE_BUCKET       = module.data_lake_bucket.bucket_name
    RAW_PREFIX             = local.raw_prefix
    BRONZE_PREFIX          = local.bronze_prefix
    SILVER_VALID_PREFIX    = local.silver_valid_prefix
    SILVER_REJECTED_PREFIX = local.silver_rejected_prefix
    ERRORS_PREFIX          = local.errors_prefix
    BEDROCK_MODEL_ID       = var.bedrock_model_id
    TRACEABILITY_MODE      = "run_id_ready"
  }
  tags = local.common_tags
}

module "extract_ocr_lambda" {
  source = "../../modules/lambda_function"

  function_name    = "${local.name_prefix}-extract-ocr"
  role_arn         = module.extract_ocr_role.role_arn
  s3_bucket        = module.artifact_bucket.bucket_name
  s3_key           = var.lambda_package_s3_key
  source_code_hash = filebase64sha256("${path.root}/../../../artifacts/lambda/control_plane_bundle.zip")
  runtime          = var.lambda_runtime
  handler          = var.extract_ocr_handler
  timeout          = var.lambda_timeout_seconds
  memory_size      = var.lambda_memory_size
  log_group_name   = module.extract_ocr_log_group.name
  environment_variables = {
    DATA_LAKE_BUCKET       = module.data_lake_bucket.bucket_name
    RAW_PREFIX             = local.raw_prefix
    BRONZE_PREFIX          = local.bronze_prefix
    SILVER_VALID_PREFIX    = local.silver_valid_prefix
    SILVER_REJECTED_PREFIX = local.silver_rejected_prefix
    ERRORS_PREFIX          = local.errors_prefix
    TRACEABILITY_MODE      = "execution_id_ready"
  }
  tags = local.common_tags
}

module "enrich_llm_lambda" {
  source = "../../modules/lambda_function"

  function_name    = "${local.name_prefix}-enrich-llm"
  role_arn         = module.enrich_llm_role.role_arn
  s3_bucket        = module.artifact_bucket.bucket_name
  s3_key           = var.lambda_package_s3_key
  source_code_hash = filebase64sha256("${path.root}/../../../artifacts/lambda/control_plane_bundle.zip")
  runtime          = var.lambda_runtime
  handler          = var.enrich_llm_handler
  timeout          = var.lambda_timeout_seconds
  memory_size      = var.lambda_memory_size
  log_group_name   = module.enrich_llm_log_group.name
  environment_variables = {
    DATA_LAKE_BUCKET       = module.data_lake_bucket.bucket_name
    BRONZE_PREFIX          = local.bronze_prefix
    SILVER_VALID_PREFIX    = local.silver_valid_prefix
    SILVER_REJECTED_PREFIX = local.silver_rejected_prefix
    ERRORS_PREFIX          = local.errors_prefix
    BEDROCK_MODEL_ID       = var.bedrock_model_id
    TRACEABILITY_MODE      = "execution_id_ready"
  }
  tags = local.common_tags
}

module "publish_metrics_lambda" {
  source = "../../modules/lambda_function"

  function_name    = "${local.name_prefix}-publish-metrics"
  role_arn         = module.publish_metrics_role.role_arn
  s3_bucket        = module.artifact_bucket.bucket_name
  s3_key           = var.lambda_package_s3_key
  source_code_hash = filebase64sha256("${path.root}/../../../artifacts/lambda/control_plane_bundle.zip")
  runtime          = var.lambda_runtime
  handler          = var.publish_metrics_handler
  timeout          = var.lambda_timeout_seconds
  memory_size      = var.lambda_memory_size
  log_group_name   = module.publish_metrics_log_group.name
  environment_variables = {
    CLOUDWATCH_NAMESPACE = var.cloudwatch_namespace
  }
  tags = local.common_tags
}

module "consolidate_gold_lambda" {
  source = "../../modules/lambda_function"

  function_name    = "${local.name_prefix}-consolidate-gold"
  role_arn         = module.consolidate_gold_role.role_arn
  s3_bucket        = module.artifact_bucket.bucket_name
  s3_key           = var.lambda_package_s3_key
  source_code_hash = filebase64sha256("${path.root}/../../../artifacts/lambda/control_plane_bundle.zip")
  runtime          = var.lambda_runtime
  handler          = var.consolidate_gold_handler
  timeout          = var.lambda_timeout_seconds
  memory_size      = var.lambda_memory_size
  log_group_name   = module.consolidate_gold_log_group.name
  environment_variables = {
    DATA_LAKE_BUCKET       = module.data_lake_bucket.bucket_name
    SILVER_VALID_PREFIX    = local.silver_valid_prefix
    SILVER_REJECTED_PREFIX = local.silver_rejected_prefix
    ERRORS_PREFIX          = local.errors_prefix
    GOLD_PREFIX            = local.gold_prefix
    GOLD_MANIFEST_PREFIX   = local.gold_manifest_prefix
    TRACEABILITY_MODE      = "batch_id_ready"
  }
  tags = local.common_tags
}

resource "aws_s3_bucket_notification" "raw_upload" {
  bucket = module.data_lake_bucket.bucket_id

  queue {
    queue_arn     = module.raw_ingestion_queue.queue_arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "${local.raw_prefix}/"
    filter_suffix = var.raw_trigger_suffix
  }

  depends_on = [aws_sqs_queue_policy.raw_ingestion]
}

resource "aws_lambda_event_source_mapping" "raw_dispatch_sqs" {
  event_source_arn        = module.raw_ingestion_queue.queue_arn
  function_name           = module.raw_dispatch_lambda.lambda_arn
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]

  scaling_config {
    maximum_concurrency = 5
  }

  depends_on = [module.raw_dispatch_role]
}

module "textract_permissions" {
  source = "../../modules/textract_permissions"

  name                 = "${local.name_prefix}-textract"
  data_lake_bucket_arn = module.data_lake_bucket.bucket_arn
  raw_prefix           = local.raw_prefix
  bronze_prefix        = local.bronze_prefix
  attach_to_role_names = [
    module.process_document_role.role_name,
    module.extract_ocr_role.role_name,
  ]
  tags = local.common_tags
}

module "bedrock_permissions" {
  source = "../../modules/bedrock_permissions"

  name       = "${local.name_prefix}-bedrock"
  aws_region = var.aws_region
  account_id = data.aws_caller_identity.current.account_id
  model_id   = var.bedrock_model_id
  attach_to_role_names = [
    module.process_document_role.role_name,
    module.enrich_llm_role.role_name,
  ]
  tags = local.common_tags
}
