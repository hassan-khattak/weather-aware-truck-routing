# Cost guard. Requires "Receive Billing Alerts" to be enabled once in the account's billing settings.

resource "aws_sns_topic" "billing" {
  provider = aws.billing
  name     = "${var.prefix}-billing"
}

resource "aws_sns_topic_subscription" "billing_email" {
  provider  = aws.billing
  topic_arn = aws_sns_topic.billing.arn
  protocol  = "email"
  endpoint  = var.billing_alarm_email
}

resource "aws_cloudwatch_metric_alarm" "billing" {
  provider            = aws.billing
  alarm_name          = "${var.prefix}-estimated-charges"
  namespace           = "AWS/Billing"
  metric_name         = "EstimatedCharges"
  statistic           = "Maximum"
  period              = 21600
  evaluation_periods  = 1
  threshold           = var.billing_alarm_usd
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = [aws_sns_topic.billing.arn]

  dimensions = {
    Currency = "USD"
  }
}
