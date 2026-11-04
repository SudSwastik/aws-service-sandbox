# API Gateway → Lambda mock API

A dependency-free Python Lambda handler for testing GET, POST, PUT, and DELETE
through API Gateway. Every path uses the same mock behavior. Responses include
the method, path, query parameters, path parameters, and parsed request body so
you can inspect what API Gateway forwarded.

This mock is stateless: POST, PUT, and DELETE do not store or change anything.
GET always returns the same sample item. Headers and credentials are not echoed.

## Project layout

```text
api-gateway-lambda-passthrough/
  lambda/
    lambda_function.py          # Lambda handler source
  api-gateway/
    openapi.yaml                # HTTP routes and Lambda integration definition
  terraform/
    README.md                   # Deployment walkthrough
    main.tf                     # AWS resources and connections
    variables.tf                # Region and naming inputs
    outputs.tf                  # Deployed URLs and resource names
    versions.tf                 # Provider configuration
    terraform.example.tfvars    # Example local settings
  README.md                     # Overview and manual testing
```

Lambda source, API definitions, and infrastructure each have their own folder.
Keep future integrations in their own top-level project directory using the
same grouping. Terraform commands still run from `terraform/`.

## Deploy everything with Terraform

See the [beginner Terraform walkthrough](terraform/README.md) to create the
Lambda, HTTP API, four routes, execution role, logs, and invocation permission
together. Terraform connects the routes automatically; no manual attachment is
required. This creates a separate setup from the resources you created manually.

With Terraform and the AWS CLI installed and an AWS profile configured, run
from the repository root:

```sh
export AWS_PROFILE=your-sandbox-profile
aws sts get-caller-identity
cd api-gateway-lambda-passthrough/terraform
cp -n terraform.example.tfvars terraform.tfvars
terraform init
terraform validate
terraform plan -out=deployment.tfplan
terraform apply deployment.tfplan
export API_URL="$(terraform output -raw api_url)"
curl -sS "$API_URL/items" | jq .
```

Review `terraform.tfvars` for the intended region and resource name before
planning. Review the saved plan before applying: applying a saved plan does
not ask for another confirmation. This creates billable AWS resources.

## Lambda setup

1. Create a Lambda function using a supported Python runtime and a basic
   execution role with CloudWatch Logs permissions. No database or other AWS
   service permissions are needed by this code.
2. Paste `lambda/lambda_function.py` into the Lambda code editor and deploy the code.
3. Set the handler to `lambda_function.lambda_handler`.
4. Connect API Gateway using a **Lambda proxy integration**. The handler accepts
   REST API proxy events and HTTP API payload versions 1.0 and 2.0.
5. For an HTTP API, connect `ANY /{proxy+}` to the function; add `ANY /` if you
   also want to test the root path. For a REST API, use an `ANY` method on a
   `/{proxy+}` resource with Lambda proxy integration enabled, then deploy the
   API to a stage. Ensure API Gateway has permission to invoke the function.

Reference: [AWS Lambda proxy payload formats](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-lambda.html).

## Import API Gateway from OpenAPI

Instead of creating routes manually, use the included `api-gateway/openapi.yaml` to create
an **HTTP API**. It defines `GET /items`, `POST /items`, `PUT /items/{id}`, and
`DELETE /items/{id}`, all connected to the same Lambda proxy integration.

1. Deploy the Lambda code as described above.
2. Replace `YOUR_REGION`, `YOUR_ACCOUNT_ID`, and `YOUR_FUNCTION_NAME` throughout
   `api-gateway/openapi.yaml` with your Lambda's values.
3. In API Gateway, choose to import an HTTP API and upload `api-gateway/openapi.yaml`, or
   run the commands below from this directory with your AWS profile configured.

```sh
export AWS_REGION='your-region'
export FUNCTION_NAME='your-function-name'
export ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"

export API_ID="$(aws apigatewayv2 import-api \
  --body file://api-gateway/openapi.yaml --fail-on-warnings \
  --query ApiId --output text)"

aws lambda add-permission \
  --function-name "$FUNCTION_NAME" \
  --statement-id "api-gateway-$API_ID" \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-account "$ACCOUNT_ID" \
  --source-arn "arn:aws:execute-api:$AWS_REGION:$ACCOUNT_ID:$API_ID/*/*/items*"

aws apigatewayv2 create-stage \
  --api-id "$API_ID" --stage-name '$default' --auto-deploy

export API_URL="https://$API_ID.execute-api.$AWS_REGION.amazonaws.com"
```

These commands create live AWS resources. Use the same region and account as
the Lambda and the values substituted into the OpenAPI file. Importing the
definition alone does not grant Lambda invocation permission or create a stage;
complete those steps even when importing through the console. The example ARN
format assumes the standard AWS partition. Routes have no API authorizer.

AWS reference: [Importing OpenAPI definitions for HTTP APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-open-api.html).

## Try the endpoints

Replace the URL with your API's invoke URL, without a trailing slash. For the
`$default` stage, use the base URL shown below. For a named stage, append the
stage name, for example `https://YOUR_API_ID.execute-api.YOUR_REGION.amazonaws.com/dev`.

These commands require `jq` and pretty-print the JSON response body.

```sh
export API_URL='https://YOUR_API_ID.execute-api.YOUR_REGION.amazonaws.com'

# GET — expect 200
curl -sS "$API_URL/items?status=active" | jq .

# POST — expect 201
curl -sS -X POST "$API_URL/items" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Test item","status":"active"}' | jq .

# PUT — expect 200
curl -sS -X PUT "$API_URL/items/1" \
  -H 'Content-Type: application/json' \
  -d '{"id":"1","name":"Updated item","status":"inactive"}' | jq .

# DELETE — expect 200
curl -sS -X DELETE "$API_URL/items/1" | jq .
```

| Method | Expected status | Mock result |
| --- | --- | --- |
| GET | 200 | Fixed sample item list |
| POST | 201 | Submitted object, with a default `mock-id` if no ID was supplied |
| PUT | 200 | Submitted object |
| DELETE | 200 | `{"deleted": true}` |

POST and PUT require a JSON object. Invalid JSON or invalid base64 encoding
returns 400. Unsupported methods return 405 if routed to this handler.
Base64-encoded UTF-8 JSON request bodies are supported.

For a Lambda console test, use this REST API proxy event and change the method,
path, and body to try the other operations:

```json
{
  "httpMethod": "POST",
  "path": "/items",
  "queryStringParameters": null,
  "body": "{\"name\":\"New item\"}",
  "isBase64Encoded": false
}
```

In the Lambda console, `body` in the returned proxy response is a JSON string.
Through API Gateway, clients receive that string as the HTTP response body.
Inspect the `request` field to verify forwarding. Lambda invocation logs appear
in CloudWatch Logs under `/aws/lambda/<function-name>`.

## Cleanup

For a Terraform deployment, run from `terraform/`:

```sh
terraform destroy
```

Review and confirm the deletion. Keep your state files until cleanup is complete.
An externally supplied execution role is not deleted by Terraform.

For a manual deployment, delete the API and Lambda function, along with any
experiment-owned execution role and CloudWatch log group you no longer need.
API requests, Lambda invocations, and retained logs can incur charges.
