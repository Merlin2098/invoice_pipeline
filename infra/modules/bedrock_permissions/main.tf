locals {
  foundation_model_resource       = "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.model_id}"
  inference_profile_resource      = "arn:aws:bedrock:${var.aws_region}:${var.account_id}:inference-profile/${var.model_id}"
  cross_region_inference_wildcard = "arn:aws:bedrock:*::foundation-model/*"
  model_resources = var.model_arn_override != null ? [var.model_arn_override] : [
    local.foundation_model_resource,
    local.inference_profile_resource,
    local.cross_region_inference_wildcard,
  ]
}

data "aws_iam_policy_document" "this" {
  statement {
    sid = "AllowModelInvocation"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = local.model_resources
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
