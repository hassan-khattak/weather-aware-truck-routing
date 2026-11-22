output "app_url" {
  value = "https://${aws_cloudfront_distribution.app.domain_name}"
}

output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.app.id
}

output "web_bucket" {
  value = aws_s3_bucket.web.id
}

output "ecr_repository_url" {
  value = aws_ecr_repository.backend.repository_url
}

output "instance_id" {
  value = aws_instance.app.id
}

output "elastic_ip" {
  value = aws_eip.app.public_ip
}

output "deploy_role_arn" {
  value = aws_iam_role.deploy.arn
}
