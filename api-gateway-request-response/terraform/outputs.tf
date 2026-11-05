output "api_url" {
  value = aws_api_gateway_stage.api.invoke_url
}

output "api_key" {
  description = "Keep private. Stored in ignored Terraform state."
  value       = aws_api_gateway_api_key.client.value
  sensitive   = true
}

output "lambda_log_group" {
  value = aws_cloudwatch_log_group.backend.name
}

output "aws_region" {
  value = var.aws_region
}
