resource "aws_cloudwatch_metric_alarm" "documents_failed" {
  alarm_name          = "${var.name_prefix}-documents-failed"
  alarm_description   = "Documents failed in the invoice pipeline."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "DocumentsFailed"
  namespace           = var.namespace
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "unknown_document_type_rate" {
  alarm_name          = "${var.name_prefix}-unknown-document-type-rate"
  alarm_description   = "Unknown document type rate exceeded the configured threshold."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "UnknownDocumentTypeRate"
  namespace           = var.namespace
  period              = 300
  statistic           = "Average"
  threshold           = 0.2
  treat_missing_data  = "notBreaching"
  tags                = var.tags
}

