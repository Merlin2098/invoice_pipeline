locals {
  site_bucket_name = "${local.name_prefix}-${data.aws_caller_identity.current.account_id}-site"
}

# ──────────────────────────────────────────────────────────────
# S3 static site bucket (private — served exclusively via CloudFront OAC)
# ──────────────────────────────────────────────────────────────

module "site_bucket" {
  source = "../../modules/s3_bucket"

  bucket_name   = local.site_bucket_name
  force_destroy = var.force_destroy
  tags          = local.common_tags
}

resource "aws_s3_bucket_website_configuration" "site" {
  bucket = module.site_bucket.bucket_id

  index_document { suffix = "index.html" }
  error_document { key = "index.html" }
}

# ──────────────────────────────────────────────────────────────
# CloudFront Origin Access Control
# ──────────────────────────────────────────────────────────────

resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "${local.name_prefix}-site-oac"
  description                       = "OAC for the invoice portal static site bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# ──────────────────────────────────────────────────────────────
# S3 bucket policy: allow only CloudFront distribution
# ──────────────────────────────────────────────────────────────

data "aws_iam_policy_document" "site_bucket_policy" {
  statement {
    sid     = "AllowCloudFrontServicePrincipal"
    actions = ["s3:GetObject"]
    resources = ["${module.site_bucket.bucket_arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.site.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "site" {
  bucket = module.site_bucket.bucket_id
  policy = data.aws_iam_policy_document.site_bucket_policy.json

  depends_on = [aws_cloudfront_distribution.site]
}

# ──────────────────────────────────────────────────────────────
# WAF Web ACL (rate limiting — protects Bedrock/Athena spend)
# CloudFront WAF must be in us-east-1 (global scope)
# ──────────────────────────────────────────────────────────────

resource "aws_wafv2_web_acl" "portal" {
  name  = "${local.name_prefix}-portal-waf"
  scope = "CLOUDFRONT"

  default_action {
    allow {}
  }

  rule {
    name     = "RateLimitPerIP"
    priority = 1

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = var.waf_rate_limit
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.name_prefix}-rate-limit"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${local.name_prefix}-portal-waf"
    sampled_requests_enabled   = true
  }

  tags = local.common_tags
}

# ──────────────────────────────────────────────────────────────
# CloudFront distribution
# ──────────────────────────────────────────────────────────────

resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  price_class         = "PriceClass_100"
  web_acl_id          = aws_wafv2_web_acl.portal.arn
  comment             = "${local.name_prefix} invoice portal"

  origin {
    domain_name              = module.site_bucket.bucket_id != null ? "${module.site_bucket.bucket_id}.s3.${var.aws_region}.amazonaws.com" : ""
    origin_id                = "S3SiteBucket"
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  # API Gateway origin for /uploads, /invoices, /chat
  origin {
    domain_name = replace(replace(aws_apigatewayv2_stage.default.invoke_url, "https://", ""), "/${aws_apigatewayv2_stage.default.name}", "")
    origin_id   = "WebAPI"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = "S3SiteBucket"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }

    min_ttl     = 0
    default_ttl = 3600
    max_ttl     = 86400
  }

  # API routes bypass cache and forward to API Gateway
  ordered_cache_behavior {
    path_pattern           = "/uploads*"
    target_origin_id       = "WebAPI"
    viewer_protocol_policy = "https-only"
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    forwarded_values {
      query_string = true
      headers      = ["Origin", "Authorization", "Content-Type"]
      cookies { forward = "none" }
    }

    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0
  }

  ordered_cache_behavior {
    path_pattern           = "/invoices*"
    target_origin_id       = "WebAPI"
    viewer_protocol_policy = "https-only"
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    forwarded_values {
      query_string = true
      headers      = ["Origin", "Authorization", "Content-Type"]
      cookies { forward = "none" }
    }

    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0
  }

  ordered_cache_behavior {
    path_pattern           = "/chat*"
    target_origin_id       = "WebAPI"
    viewer_protocol_policy = "https-only"
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    forwarded_values {
      query_string = true
      headers      = ["Origin", "Authorization", "Content-Type"]
      cookies { forward = "none" }
    }

    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0
  }

  # SPA fallback: all unknown paths serve index.html
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = local.common_tags
}

# ──────────────────────────────────────────────────────────────
# CloudWatch alarms
# ──────────────────────────────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "dlq_depth" {
  alarm_name          = "${local.name_prefix}-dlq-depth"
  alarm_description   = "DLQ has messages — pipeline documents failed raw dispatch."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = element(split("/", module.raw_ingestion_queue.dlq_url), length(split("/", module.raw_ingestion_queue.dlq_url)) - 1)
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = {
    upload         = module.upload_lambda.lambda_name
    invoice_status = module.invoice_status_lambda.lambda_name
    list_invoices  = module.list_invoices_lambda.lambda_name
    chat           = module.chat_lambda.lambda_name
  }

  alarm_name          = "${local.name_prefix}-lambda-errors-${each.key}"
  alarm_description   = "Lambda ${each.value} has errors."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = each.value
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "sfn_failures" {
  alarm_name          = "${local.name_prefix}-sfn-failures"
  alarm_description   = "Step Functions executions are failing."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsFailed"
  namespace           = "AWS/States"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    StateMachineArn = module.invoice_pipeline_state_machine.state_machine_arn
  }

  tags = local.common_tags
}
