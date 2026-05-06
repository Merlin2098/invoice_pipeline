data "aws_iam_policy_document" "sfn_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "sfn_access" {
  statement {
    actions = [
      "lambda:InvokeFunction",
    ]
    resources = [
      var.prevalidation_lambda_arn,
      var.publish_metrics_lambda_arn,
    ]
  }

  statement {
    actions = [
      "glue:StartJobRun",
      "glue:GetJobRun",
      "glue:GetJobRuns",
      "glue:BatchStopJobRun",
    ]
    resources = ["*"]
  }

  statement {
    actions = [
      "textract:AnalyzeExpense",
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = ["*"]
  }

  statement {
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role" "state_machine" {
  name               = "${var.name_prefix}-sfn-role"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume_role.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "state_machine_access" {
  name   = "${var.name_prefix}-sfn-access"
  role   = aws_iam_role.state_machine.id
  policy = data.aws_iam_policy_document.sfn_access.json
}

resource "aws_cloudwatch_log_group" "state_machine" {
  name              = var.state_machine_log_group_name
  retention_in_days = 30
  tags              = var.tags
}

resource "aws_sfn_state_machine" "invoice_pipeline" {
  name     = "${var.name_prefix}-state-machine"
  role_arn = aws_iam_role.state_machine.arn
  type     = "STANDARD"

  definition = templatefile("${path.module}/state_machine.asl.json", {
    data_lake_bucket_name      = var.data_lake_bucket_name
    prevalidation_lambda_arn   = var.prevalidation_lambda_arn
    publish_metrics_lambda_arn = var.publish_metrics_lambda_arn
    normalize_job_name         = var.normalize_job_name
    consolidate_job_name       = var.consolidate_job_name
    bedrock_model_id           = var.bedrock_model_id
  })

  logging_configuration {
    level                  = "ALL"
    include_execution_data = true

    log_destination = "${aws_cloudwatch_log_group.state_machine.arn}:*"
  }

  tags = var.tags
}

