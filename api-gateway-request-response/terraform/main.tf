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
      Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole"
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
      Effect   = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"],
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
  depends_on       = [aws_iam_role_policy.logs]
}

locals {
  definition = yamldecode(replace(file("${path.module}/../api-gateway/openapi.yaml"),
  "YOUR_BACKEND_INVOKE_ARN", aws_lambda_function.backend.invoke_arn))
}

resource "aws_api_gateway_rest_api" "api" {
  name = var.project_name
  body = jsonencode(merge(local.definition, {
    info = merge(local.definition.info, { title = var.project_name })
  }))
  put_rest_api_mode = "overwrite"
  fail_on_warnings  = true
  api_key_source    = "HEADER"
  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

resource "aws_lambda_permission" "gateway" {
  statement_id   = "AllowRestApi"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.backend.function_name
  principal      = "apigateway.amazonaws.com"
  source_account = data.aws_caller_identity.current.account_id
  source_arn     = "${aws_api_gateway_rest_api.api.execution_arn}/*/*/*"
}

resource "aws_api_gateway_deployment" "api" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  triggers = {
    definition = sha1(aws_api_gateway_rest_api.api.body)
  }
  lifecycle {
    create_before_destroy = true
  }
  depends_on = [aws_lambda_permission.gateway]
}

resource "aws_api_gateway_stage" "api" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  deployment_id = aws_api_gateway_deployment.api.id
  stage_name    = var.stage_name
}

resource "aws_api_gateway_method_settings" "all" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  stage_name  = aws_api_gateway_stage.api.stage_name
  method_path = "*/*"
  settings {
    throttling_rate_limit  = 50
    throttling_burst_limit = 100
    # Do not enable payload tracing: requests may contain credentials.
    data_trace_enabled = false
  }
}

resource "aws_api_gateway_api_key" "client" {
  name    = "${var.project_name}-client"
  enabled = true
  # AWS generates the value; no key is hardcoded in source.
}

resource "aws_api_gateway_usage_plan" "client" {
  name = "${var.project_name}-plan"
  api_stages {
    api_id = aws_api_gateway_rest_api.api.id
    stage  = aws_api_gateway_stage.api.stage_name
  }
  throttle_settings {
    rate_limit  = var.rate_limit
    burst_limit = var.burst_limit
  }
  quota_settings {
    limit  = var.daily_quota
    period = "DAY"
  }
}

resource "aws_api_gateway_usage_plan_key" "client" {
  key_id        = aws_api_gateway_api_key.client.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.client.id
}
