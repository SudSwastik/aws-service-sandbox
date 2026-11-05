output "api_url" {
  description = "REST API base URL, already including its stage."
  value       = aws_api_gateway_stage.items.invoke_url
}

output "user_pool_id" {
  description = "User pool used by the test-user creation helper."
  value       = aws_cognito_user_pool.users.id
}

output "client_id" {
  description = "Public app client ID used to sign in; this is not a client secret."
  value       = aws_cognito_user_pool_client.cli.id
}

output "aws_region" {
  description = "Region used for Cognito and the API."
  value       = var.aws_region
}

output "lambda_function_name" {
  description = "Backend Lambda; no authorizer Lambda is used in this project."
  value       = aws_lambda_function.backend.function_name
}

output "lambda_log_group" {
  description = "Backend CloudWatch log group."
  value       = aws_cloudwatch_log_group.backend.name
}
