data "aws_iam_policy_document" "assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "logging" {
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

resource "aws_iam_role" "this" {
  name               = "${var.state_machine_name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "logging" {
  name   = "${var.state_machine_name}-logging"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.logging.json
}

resource "aws_iam_role_policy" "additional" {
  for_each = var.additional_inline_policies

  name   = each.key
  role   = aws_iam_role.this.id
  policy = each.value
}

resource "aws_iam_role_policy_attachment" "managed" {
  for_each = toset(var.managed_policy_arns)

  role       = aws_iam_role.this.name
  policy_arn = each.value
}

resource "aws_cloudwatch_log_group" "this" {
  name              = var.log_group_name
  retention_in_days = var.log_retention_in_days
  tags              = var.tags
}

resource "aws_sfn_state_machine" "this" {
  name     = var.state_machine_name
  role_arn = aws_iam_role.this.arn
  type     = var.type

  definition = var.definition

  logging_configuration {
    level                  = var.logging_level
    include_execution_data = var.include_execution_data
    log_destination        = "${aws_cloudwatch_log_group.this.arn}:*"
  }

  tags = var.tags
}
