output "api_url" {
  description = "API base URL. Append /items; no stage suffix is needed."
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "lambda_function_name" {
  description = "Name of the deployed mock Lambda."
  value       = aws_lambda_function.mock.function_name
}

output "lambda_log_group" {
  description = "CloudWatch log group for Lambda invocation logs."
  value       = aws_cloudwatch_log_group.lambda.name
}

output "aws_region" {
  description = "Region containing the deployed resources."
  value       = var.aws_region
}
