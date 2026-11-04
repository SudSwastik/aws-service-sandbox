data "aws_caller_identity" "current" {}

# Package only the handler, without local caches or documentation.
data "archive_file" "lambda" {
  type        = "zip"
  source_file = "${path.module}/../lambda/lambda_function.py"
  output_path = "${path.module}/lambda.zip"
}

# The execution role tells AWS that Lambda may assume this identity.
resource "aws_iam_role" "lambda" {
  count = var.existing_lambda_role_arn == null ? 1 : 0

  name = "${var.project_name}-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project_name}"
  retention_in_days = 7
}

# Lambda can write only to this experiment's log group.
resource "aws_iam_role_policy" "logs" {
  count = var.existing_lambda_role_arn == null ? 1 : 0

  name = "write-lambda-logs"
  role = aws_iam_role.lambda[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "${aws_cloudwatch_log_group.lambda.arn}:*"
    }]
  })
}

resource "aws_lambda_function" "mock" {
  function_name    = var.project_name
  role             = var.existing_lambda_role_arn != null ? var.existing_lambda_role_arn : aws_iam_role.lambda[0].arn
  runtime          = "python3.13"
  handler          = "lambda_function.lambda_handler"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  memory_size      = 128
  timeout          = 10

  depends_on = [aws_iam_role_policy.logs]
}

# Preserve resource addresses for setups created before role reuse was added.
moved {
  from = aws_iam_role.lambda
  to   = aws_iam_role.lambda[0]
}

moved {
  from = aws_iam_role_policy.logs
  to   = aws_iam_role_policy.logs[0]
}

# Reuse the OpenAPI YAML and fill in deployment-specific values in memory.
# The checked-in YAML remains usable for manual imports.
locals {
  openapi_body = replace(
    replace(
      replace(file("${path.module}/../api-gateway/openapi.yaml"), "YOUR_REGION", var.aws_region),
      "YOUR_ACCOUNT_ID", data.aws_caller_identity.current.account_id
    ),
    "YOUR_FUNCTION_NAME", aws_lambda_function.mock.function_name
  )
}

resource "aws_apigatewayv2_api" "mock" {
  name          = var.project_name
  protocol_type = "HTTP"
  body          = jsonencode(yamldecode(local.openapi_body))
}

# This is separate from the execution role: it lets API Gateway call Lambda.
resource "aws_lambda_permission" "api_gateway" {
  statement_id   = "AllowMockApiGateway"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.mock.function_name
  principal      = "apigateway.amazonaws.com"
  source_account = data.aws_caller_identity.current.account_id
  source_arn     = "${aws_apigatewayv2_api.mock.execution_arn}/*/*/items*"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.mock.id
  name        = "$default"
  auto_deploy = true

  depends_on = [aws_lambda_permission.api_gateway]
}
