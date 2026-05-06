locals {
  model_resource = coalesce(
    var.model_arn_override,
    "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.model_id}"
  )
}

data "aws_iam_policy_document" "this" {
  statement {
    sid = "AllowModelInvocation"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = [local.model_resource]
  }
}

resource "aws_iam_policy" "this" {
  name   = var.name
  policy = data.aws_iam_policy_document.this.json
  tags   = var.tags
}

resource "aws_iam_role_policy_attachment" "this" {
  for_each = toset(var.attach_to_role_names)

  role       = each.value
  policy_arn = aws_iam_policy.this.arn
}
