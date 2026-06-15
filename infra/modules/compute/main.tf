data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "glue_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "lambda_access" {
  statement {
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = ["${var.data_lake_bucket_arn}/*"]
  }

  statement {
    actions   = ["s3:ListBucket"]
    resources = [var.data_lake_bucket_arn]
  }

  statement {
    actions = [
      "cloudwatch:PutMetricData",
    ]
    resources = ["*"]
  }
}

data "aws_iam_policy_document" "glue_access" {
  statement {
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = ["${var.artifact_bucket_arn}/*"]
  }

  statement {
    actions   = ["s3:ListBucket"]
    resources = [var.artifact_bucket_arn]
  }

  statement {
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = ["${var.data_lake_bucket_arn}/*"]
  }

  statement {
    actions   = ["s3:ListBucket"]
    resources = [var.data_lake_bucket_arn]
  }

  statement {
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role" "lambda_execution" {
  name               = "${var.name_prefix}-lambda-control-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_access" {
  name   = "${var.name_prefix}-lambda-access"
  role   = aws_iam_role.lambda_execution.id
  policy = data.aws_iam_policy_document.lambda_access.json
}

resource "aws_lambda_function" "prevalidation" {
  function_name = "${var.name_prefix}-prevalidation"
  s3_bucket     = var.artifact_bucket_name
  s3_key        = var.lambda_package_s3_key
  role          = aws_iam_role.lambda_execution.arn
  runtime       = "python3.11"
  handler       = "src.aws.lambda_handlers.control_plane.validate_input"
  timeout       = 60
  tags          = var.tags

  environment {
    variables = {
      DATA_LAKE_BUCKET     = var.data_lake_bucket_name
      CLOUDWATCH_NAMESPACE = var.cloudwatch_namespace
      BEDROCK_MODEL_ID     = var.bedrock_model_id
    }
  }
}

resource "aws_lambda_function" "publish_metrics" {
  function_name = "${var.name_prefix}-publish-metrics"
  s3_bucket     = var.artifact_bucket_name
  s3_key        = var.lambda_package_s3_key
  role          = aws_iam_role.lambda_execution.arn
  runtime       = "python3.11"
  handler       = "src.aws.lambda_handlers.control_plane.publish_run_metrics"
  timeout       = 60
  tags          = var.tags

  environment {
    variables = {
      CLOUDWATCH_NAMESPACE = var.cloudwatch_namespace
    }
  }
}

resource "aws_iam_role" "glue_execution" {
  name               = "${var.name_prefix}-glue-role"
  assume_role_policy = data.aws_iam_policy_document.glue_assume_role.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

resource "aws_iam_role_policy" "glue_access" {
  name   = "${var.name_prefix}-glue-access"
  role   = aws_iam_role.glue_execution.id
  policy = data.aws_iam_policy_document.glue_access.json
}

resource "aws_glue_job" "normalize" {
  name         = "${var.name_prefix}-normalize"
  role_arn     = aws_iam_role.glue_execution.arn
  glue_version = "4.0"
  max_retries  = 1
  timeout      = 15

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${var.artifact_bucket_name}/${var.normalize_script_s3_key}"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--enable-continuous-cloudwatch-log" = "true"
    "--data_lake_bucket"                 = var.data_lake_bucket_name
    "--bedrock_model_id"                 = var.bedrock_model_id
  }

  tags = var.tags
}

resource "aws_glue_job" "consolidate" {
  name         = "${var.name_prefix}-consolidate"
  role_arn     = aws_iam_role.glue_execution.arn
  glue_version = "4.0"
  max_retries  = 1
  timeout      = 15

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${var.artifact_bucket_name}/${var.consolidate_script_s3_key}"
  }

  default_arguments = {
    "--job-language"     = "python"
    "--data_lake_bucket" = var.data_lake_bucket_name
  }

  tags = var.tags
}
