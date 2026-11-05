data "aws_caller_identity" "current" {}

data "archive_file" "backend" {
  type        = "zip"
  source_file = "${path.module}/../lambda/backend/lambda_function.py"
  output_path = "${path.module}/backend.zip"
}

resource "aws_iam_role" "backend" {
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

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/aws/lambda/${var.project_name}-backend"
  retention_in_days = 7
}

resource "aws_iam_role_policy" "logs" {
  name = "write-lambda-logs"
  role = aws_iam_role.backend.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "${aws_cloudwatch_log_group.backend.arn}:*"
    }]
  })
}

resource "aws_lambda_function" "backend" {
  function_name    = "${var.project_name}-backend"
  role             = aws_iam_role.backend.arn
  runtime          = "python3.13"
  handler          = "lambda_function.lambda_handler"
  filename         = data.archive_file.backend.output_path
  source_code_hash = data.archive_file.backend.output_base64sha256
  memory_size      = 128
  timeout          = 10

  depends_on = [aws_iam_role_policy.logs]
}

locals {
  openapi_body = replace(
    replace(
      replace(
        file("${path.module}/../api-gateway/openapi.yaml"),
        "YOUR_BACKEND_INVOKE_ARN", aws_lambda_function.backend.invoke_arn
      ),
      "YOUR_USER_POOL_ARN", aws_cognito_user_pool.users.arn
    ),
    "YOUR_CLIENT_ID", aws_cognito_user_pool_client.cli.id
  )

  openapi_definition = yamldecode(local.openapi_body)
}

resource "aws_api_gateway_rest_api" "items" {
  name = var.project_name
  body = jsonencode(merge(local.openapi_definition, {
    info = merge(local.openapi_definition.info, { title = var.project_name })
  }))
  put_rest_api_mode = "overwrite"

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id   = "AllowCognitoRestApi"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.backend.function_name
  principal      = "apigateway.amazonaws.com"
  source_account = data.aws_caller_identity.current.account_id
  source_arn     = "${aws_api_gateway_rest_api.items.execution_arn}/*/*/items*"
}

resource "aws_api_gateway_deployment" "items" {
  rest_api_id = aws_api_gateway_rest_api.items.id

  triggers = {
    openapi = sha1(aws_api_gateway_rest_api.items.body)
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [aws_lambda_permission.api_gateway]
}

resource "aws_api_gateway_stage" "items" {
  rest_api_id   = aws_api_gateway_rest_api.items.id
  deployment_id = aws_api_gateway_deployment.items.id
  stage_name    = var.stage_name
}
