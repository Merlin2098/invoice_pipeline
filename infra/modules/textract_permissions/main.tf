locals {
  raw_prefix    = trim(var.raw_prefix, "/")
  bronze_prefix = trim(var.bronze_prefix, "/")
}

data "aws_iam_policy_document" "this" {
  statement {
    sid       = "AllowAnalyzeExpense"
    actions   = ["textract:AnalyzeExpense"]
    resources = ["*"]
  }

  statement {
    sid       = "ReadRawObjects"
    actions   = ["s3:GetObject"]
    resources = ["${var.data_lake_bucket_arn}/${local.raw_prefix}/*"]
  }

  statement {
    sid       = "ListRawPrefix"
    actions   = ["s3:ListBucket"]
    resources = [var.data_lake_bucket_arn]

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
    sid       = "WriteBronzeObjects"
    actions   = ["s3:PutObject"]
    resources = ["${var.data_lake_bucket_arn}/${local.bronze_prefix}/*"]
  }

  statement {
    sid       = "ListBronzePrefix"
    actions   = ["s3:ListBucket"]
    resources = [var.data_lake_bucket_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        local.bronze_prefix,
        "${local.bronze_prefix}/*",
      ]
    }
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
