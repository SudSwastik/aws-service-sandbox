output "api_url" {
  description = "REST API base URL including the stage. Append /items."
  value       = aws_api_gateway_stage.items.invoke_url
}

output "lambda_function_names" {
  description = "Separate backend and authorizer Lambda functions."
  value       = { for key, function in aws_lambda_function.function : key => function.function_name }
}

output "log_groups" {
  description = "CloudWatch log groups for troubleshooting each Lambda."
  value       = { for key, group in aws_cloudwatch_log_group.function : key => group.name }
}
