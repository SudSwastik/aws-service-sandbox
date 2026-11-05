# REST API with a Lambda authorizer

An API Gateway **REST API** with four protected item routes, a Python Lambda
backend, and a separate Python **TOKEN authorizer**. Terraform creates and
connects everything using the OpenAPI YAML.

This project is independent of `api-gateway-lambda-passthrough/`. It creates
new resources and has its own Terraform state.

## Request flow

```text
Client sends Authorization: Bearer <token>
  → API Gateway REST API
  → Authorizer Lambda checks the token
      invalid → 401 Unauthorized; backend does not run
      valid   → Allow policy for the requested method
              → Backend Lambda → mock JSON response
```

A missing Authorization header is rejected by API Gateway with 401 before
calling the TOKEN authorizer. The authorizer returns an IAM policy rather than
an HTTP response. API Gateway evaluates it before invoking the backend.

The token is a shared secret for sandbox testing. This does not validate JWTs
or provide user sign-in, token issuance, expiration, or individual user identities.
For a user-facing authentication system, replace the comparison with appropriate
identity-provider token validation or use a Cognito authorizer.

## Layout

```text
api-gateway-rest-authorizer/
  api-gateway/openapi.yaml
  lambda/
    authorizer/lambda_function.py
    backend/lambda_function.py
  terraform/
    main.tf
    variables.tf
    outputs.tf
    versions.tf
    terraform.example.tfvars
    iam/deployment-policy.example.json
  tests/test_authorizer.py
  README.md
```

## Prerequisites and permissions

Install Terraform 1.5 or newer (below 2.0), AWS CLI v2, Python 3, curl, and jq.
Use an AWS profile with permission to manage REST APIs and their deployments and
stages, Lambda functions and invocation permissions, CloudWatch log groups,
IAM execution roles and inline policies, resource tags, and `iam:PassRole`.

If you use `PowerUserAccess`, the IAM permission you previously added for
`items-api-role` does not cover this project's two roles. An administrator can
add the statements from
[deployment-policy.example.json](terraform/iam/deployment-policy.example.json)
to the deployment identity or SSO permission set. Replace `YOUR_ACCOUNT_ID`,
and adjust role names if you change `project_name`. This example adds scoped
IAM permissions; the rest of the deployment permissions must also be present.
Provision SSO permission-set changes to the account and sign in again.

The two execution roles each permit writing only to their own Lambda log group.
The backend cannot invoke the authorizer or read its environment using these roles.

## Deploy

From the repository root, select your profile and confirm the account:

```sh
export AWS_PROFILE=sandbox
# For an SSO profile; skip this command for other credential methods.
aws sso login --profile sandbox
aws sts get-caller-identity

cd api-gateway-rest-authorizer/terraform
cp -n terraform.example.tfvars terraform.tfvars
```

Edit `terraform.tfvars` if needed:

```hcl
aws_region   = "us-east-1"
project_name = "items-rest-api"
stage_name   = "dev"
```

Generate a token locally and provide it to Terraform in this terminal:

```sh
export AUTH_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export TF_VAR_auth_token="$AUTH_TOKEN"

terraform init
terraform fmt -check
terraform validate
terraform plan -out=deployment.tfplan
```

Review the plan, then deploy it:

```sh
terraform apply deployment.tfplan
export API_URL="$(terraform output -raw api_url)"
```

Applying a saved plan does not ask for another confirmation. This creates real
AWS resources that can incur charges. Keep the terminal open for the test
commands below so `AUTH_TOKEN` remains available.

The token is marked sensitive in Terraform output, but remains in the local
state, saved plan, and authorizer's Lambda environment configuration. Keep those
files local and secure. `sensitive` hides output; it does not remove secrets from
state. The repository ignores state, plans, local variables, and generated ZIPs.
The token is not returned in outputs or backend responses and is not logged by
the authorizer code.

## Test authorization

Run from `api-gateway-rest-authorizer/terraform/` in the same terminal after
deployment. Use the same `AUTH_TOKEN` generated before deploying; a different
token will return 401 unless you deploy that token first. These commands require
`jq` and pretty-print the JSON response bodies.

```sh
export API_URL="$(terraform output -raw api_url)"

# Missing token: expect HTTP 401.
curl -sS "$API_URL/items" | jq .

# Wrong token: expect HTTP 401.
curl -sS "$API_URL/items" \
  -H 'Authorization: Bearer invalid-token' | jq .

# Valid token: expect HTTP 200 and a JSON item list.
curl -sS "$API_URL/items?status=active" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq .

# Valid POST: expect HTTP 201.
curl -sS -X POST "$API_URL/items" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Test item"}' | jq .

# Valid PUT: expect HTTP 200.
curl -sS -X PUT "$API_URL/items/1" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"id":"1","name":"Updated item"}' | jq .

# Valid DELETE: expect HTTP 200.
curl -sS -X DELETE "$API_URL/items/1" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq .
```

The backend is stateless: POST, PUT, and DELETE do not persist changes.
The first two requests should return `{"message":"Unauthorized"}`. Authorized
requests should return `"mock": true` and request details in the `request` field.

To inspect HTTP status codes and headers, use `curl -i` without `jq`:

```sh
# Missing token: HTTP 401.
curl -i "$API_URL/items"

# Valid token: HTTP 200.
curl -i "$API_URL/items" -H "Authorization: Bearer $AUTH_TOKEN"
```

There is no unauthenticated health route or browser CORS configuration.

## What the YAML and Terraform do

- Global OpenAPI `security` requires `BearerAuthorizer` on all four operations.
- `components.securitySchemes` defines an Authorization header and AWS's
  `x-amazon-apigateway-authorizer` extension. Although the OpenAPI scheme type
  is `apiKey`, API Gateway uses a Lambda authorizer here; it is not a usage-plan
  API key.
- Terraform substitutes the backend and authorizer invocation ARNs into the
  YAML in memory. Keep the `YOUR_...` placeholders in the checked-in YAML.
- Each route has a Lambda proxy integration pointing to the backend. The
  authorizer is defined once and referenced through the global security rule.
- Separate Lambda resource permissions let this REST API invoke the backend
  for item paths and invoke the authorizer for authorization checks.
- Authorizer caching is disabled (`authorizerResultTtlInSeconds: 0`). Each
  supplied token is checked again; an Allow policy is scoped to the requested
  method ARN. Do not enable caching without reviewing policy scope across routes.
- REST APIs use deployment snapshots. Terraform hashes the API definition to
  create a new deployment when the YAML changes and updates the named stage.
  The output URL already includes `/dev`; do not append it again.

Default AWS names are `items-rest-api` for the API,
`items-rest-api-backend` and `items-rest-api-authorizer` for the Lambdas,
with corresponding `-role` execution roles and `/aws/lambda/<function-name>`
log groups. Logs are retained for seven days.

## Local checks and updates

From this project's root directory:

```sh
python3 -m unittest discover -s tests -v
```

These are local authorization behavior tests, not deployed AWS integration tests.
Run the curl checks after deploying to verify actual API Gateway authorization.
For errors, inspect each function's CloudWatch log group; `terraform output
log_groups` lists them. The authorizer returns `Unauthorized` for bad tokens;
configuration errors can instead produce 500 responses.

Edit source or YAML and run a fresh `terraform plan` and `terraform apply`.
Keep `TF_VAR_auth_token` set to the deployed token for subsequent operations.
Generating a new token and applying it rotates the accepted token and invalidates
the old one; a backend code update alone should not require rotation.

## Cleanup

From `terraform/`, with the token variable still set:

```sh
terraform plan -destroy
terraform destroy
unset TF_VAR_auth_token AUTH_TOKEN
```

Confirm deletion when prompted. This removes this project's API, stage,
deployment, both functions, their execution roles/policies, and log groups.
Keep state until cleanup is complete. The other HTTP API project is independent.

References: [AWS Lambda authorizers](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-use-lambda-authorizer.html),
[OpenAPI authorizer extension](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-swagger-extensions-authorizer.html),
and [Terraform REST API deployment](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/api_gateway_deployment).
