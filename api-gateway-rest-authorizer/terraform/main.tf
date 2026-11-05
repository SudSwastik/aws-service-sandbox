data "aws_caller_identity" "current" {}

locals {
  functions = toset(["backend", "authorizer"])

  openapi_body = replace(
    replace(
      file("${path.module}/../api-gateway/openapi.yaml"),
      "YOUR_BACKEND_INVOKE_ARN", aws_lambda_function.function["backend"].invoke_arn
    ),
    "YOUR_AUTHORIZER_INVOKE_ARN", aws_lambda_function.function["authorizer"].invoke_arn
  )

  openapi_definition = yamldecode(local.openapi_body)
}

data "archive_file" "function" {
  for_each = local.functions

  type        = "zip"
  source_file = "${path.module}/../lambda/${each.key}/lambda_function.py"
  output_path = "${path.module}/${each.key}.zip"
}

resource "aws_iam_role" "function" {
  for_each = local.functions

  name = "${var.project_name}-${each.key}-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_cloudwatch_log_group" "function" {
  for_each = local.functions

  name              = "/aws/lambda/${var.project_name}-${each.key}"
  retention_in_days = 7
}

resource "aws_iam_role_policy" "logs" {
  for_each = local.functions

  name = "write-lambda-logs"
  role = aws_iam_role.function[each.key].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "${aws_cloudwatch_log_group.function[each.key].arn}:*"
    }]
  })
}

resource "aws_lambda_function" "function" {
  for_each = local.functions

  function_name    = "${var.project_name}-${each.key}"
  role             = aws_iam_role.function[each.key].arn
  runtime          = "python3.13"
  handler          = "lambda_function.lambda_handler"
  filename         = data.archive_file.function[each.key].output_path
  source_code_hash = data.archive_file.function[each.key].output_base64sha256
  memory_size      = 128
  timeout          = 10

  # Only the authorizer receives the token. It is never returned as an output.
  dynamic "environment" {
    for_each = each.key == "authorizer" ? [1] : []
    content {
      variables = { AUTH_TOKEN = var.auth_token }
    }
  }

  depends_on = [aws_iam_role_policy.logs]
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

resource "aws_lambda_permission" "backend" {
  statement_id   = "AllowRestApiBackend"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.function["backend"].function_name
  principal      = "apigateway.amazonaws.com"
  source_account = data.aws_caller_identity.current.account_id
  source_arn     = "${aws_api_gateway_rest_api.items.execution_arn}/*/*/items*"
}

resource "aws_lambda_permission" "authorizer" {
  statement_id   = "AllowRestApiAuthorizer"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.function["authorizer"].function_name
  principal      = "apigateway.amazonaws.com"
  source_account = data.aws_caller_identity.current.account_id
  source_arn     = "${aws_api_gateway_rest_api.items.execution_arn}/authorizers/*"
}

resource "aws_api_gateway_deployment" "items" {
  rest_api_id = aws_api_gateway_rest_api.items.id

  triggers = {
    openapi = sha1(aws_api_gateway_rest_api.items.body)
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [aws_lambda_permission.backend, aws_lambda_permission.authorizer]
}

resource "aws_api_gateway_stage" "items" {
  rest_api_id   = aws_api_gateway_rest_api.items.id
  deployment_id = aws_api_gateway_deployment.items.id
  stage_name    = var.stage_name
}
