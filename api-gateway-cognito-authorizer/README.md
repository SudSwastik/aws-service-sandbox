# REST API with Cognito authentication

Cognito signs users in and issues signed tokens. API Gateway's built-in Cognito
authorizer validates the token before forwarding requests to the Python Lambda
backend. There is no shared static API token and no custom authorizer Lambda.

This is a separate project with its own resources and Terraform state.

## Request flow

```text
Username + password → Cognito sign-in → signed ID token

Client sends ID token → API Gateway Cognito authorizer
  invalid or expired → 401 Unauthorized
  valid              → backend Lambda → mock item response
```

The API uses identity-based authorization without OAuth scopes, so these
examples send an **ID token**, not an access token. The authorizer uses the
configured user pool and an audience check for this app client. Cognito tokens
expire; the backend does not implement token validation itself.

## Layout

```text
api-gateway-cognito-authorizer/
  api-gateway/openapi.yaml       # Protected routes and Cognito authorizer
  cognito/auth.py                # Test-user creation and sign-in helpers
  lambda/backend/lambda_function.py
  terraform/
    cognito.tf                  # User pool and public app client
    main.tf                     # Backend, REST API, and deployment
    variables.tf
    outputs.tf
    versions.tf
    terraform.example.tfvars
    iam/deployment-policy.example.json
  tests/test_auth.py
  README.md
```

## 1. Prerequisites and permissions

Install Terraform 1.5 or newer (below 2.0), AWS CLI v2, Python 3, curl, and jq.
The Python helper uses only the standard library and the installed AWS CLI.

The deployment identity needs permission to manage Cognito user pools and app
clients, API Gateway REST APIs/deployments/stages, Lambda, CloudWatch logs,
resource tags, and the backend IAM role and inline logging policy. It also needs
`iam:PassRole` for `items-cognito-api-role`.

If using `PowerUserAccess`, have an administrator add the statements from
[deployment-policy.example.json](terraform/iam/deployment-policy.example.json)
to your permission set, replacing `YOUR_ACCOUNT_ID` and adjusting the role name
if you change `project_name`. The example adds only the scoped IAM permissions;
the remaining service permissions must already be present. Provision permission
set changes to the account and refresh your SSO login.

In the AWS console, open **IAM Identity Center → Permission sets → your assigned
permission set → Inline policy**. Merge the example's statements into the
existing policy so permissions for other projects are preserved. This grants
Terraform permission to create and manage `items-cognito-api-role` and pass it
to Lambda; you do not need to create the role manually.

Test-user creation additionally requires `cognito-idp:AdminCreateUser` and
`cognito-idp:AdminSetUserPassword` on this user pool. Public user sign-in does
not require an IAM identity; the login helper sends an unsigned Cognito request.

## 2. Deploy the infrastructure

From the repository root:

```sh
export AWS_PROFILE=sandbox
# For an SSO profile; skip for other authentication methods.
aws sso login --profile sandbox
aws sts get-caller-identity

cd api-gateway-cognito-authorizer/terraform
cp -n terraform.example.tfvars terraform.tfvars
```

Replace `sandbox` with your profile name. Confirm your AWS account, then review
the local settings:

```hcl
aws_region   = "us-east-1"
project_name = "items-cognito-api"
stage_name   = "dev"
```

No password or token is needed by Terraform:

Run each command separately and continue only when it succeeds:

```sh
terraform init
terraform fmt -check
terraform validate
terraform plan -out=deployment.tfplan
```

Review the proposed resources, then deploy the saved plan:

```sh
terraform apply deployment.tfplan
```

A saved plan applies without another confirmation. This creates billable AWS
resources. Cognito user activity, API requests, Lambda, and retained logs can
incur charges. No database, custom domain, hosted login UI, or identity pool is
created. This CLI test flow uses a username and password with MFA disabled;
self-service sign-up is disabled.

## 3. Load configuration into your terminal

Run from this project's `terraform/` directory after deployment:

```sh
export AWS_REGION="$(terraform output -raw aws_region)"
export USER_POOL_ID="$(terraform output -raw user_pool_id)"
export CLIENT_ID="$(terraform output -raw client_id)"
export API_URL="$(terraform output -raw api_url)"
export TEST_USERNAME=api-test-user
```

The API URL already includes `/dev`. The app client is public and has no client
secret. Pool IDs and client IDs are configuration identifiers, not passwords.

## 4. Create a test user

```sh
python3 ../cognito/auth.py create-user
```

Enter and confirm a password when prompted. Use at least 12 characters with
uppercase, lowercase, a number, and a symbol; use printable ASCII without spaces.
The password is not displayed. Request parameters are passed through a private
temporary JSON file outside the repository, removed after each AWS CLI command.

The helper creates the user with notifications suppressed and sets a permanent
password. This completes the initial password-change requirement for this
sandbox user. Users are created after deployment, outside Terraform, so their
passwords and issued tokens do not become Terraform inputs or state values.

Run this once per username. If `UsernameExistsException` occurs, use that user's
existing password for login or choose a different `TEST_USERNAME`. If creation
succeeds but setting the password fails, fix the error and set the permanent
password through Cognito's user management before signing in.

## 5. Sign in and get an ID token

```sh
export ID_TOKEN="$(python3 ../cognito/auth.py login)"
```

Confirm a token was returned without displaying it:

```sh
test -n "$ID_TOKEN" && echo "ID token loaded" || echo "Login failed; retry before testing"
```

Enter the same user's password. The helper calls Cognito's `InitiateAuth` API
using `USER_PASSWORD_AUTH`, then returns `AuthenticationResult.IdToken`. The
shell captures it in `ID_TOKEN`; the raw token does not need to be printed.

Cognito handles password verification, JWT signing, and token issuance. API
Gateway validates the supplied JWT, including expiration and the configured
app-client audience check. The ID and access tokens expire after one hour in
this configuration. Sign in again with the command above when the ID token
expires. The helper does not persist or use the returned refresh token.

Keep the password and ID token private. Do not paste them into the README,
commit them, or share them in screenshots. The helper sends passwords through
a temporary JSON file with owner-only permissions rather than command-line
arguments. It removes the file after the command and hides raw AWS error
payloads that could repeat sensitive input. Backend responses do not echo the
Authorization header.

## 6. Test with curl and jq

Use the environment variables loaded above. In these examples, the
`Authorization` header contains the raw ID token.
Use it exactly as shown, without adding a `Bearer ` prefix. Missing and invalid
tokens should fail before the backend Lambda is invoked.

```sh
# Missing token: expect HTTP 401.
curl -sS "$API_URL/items" | jq .

# Invalid token: expect HTTP 401.
curl -sS "$API_URL/items" -H 'Authorization: invalid-token' | jq .

# Valid GET: expect HTTP 200.
curl -sS "$API_URL/items?status=active" \
  -H "Authorization: $ID_TOKEN" | jq .

# Valid POST: expect HTTP 201.
curl -sS -X POST "$API_URL/items" \
  -H "Authorization: $ID_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Test item"}' | jq .

# Valid PUT: expect HTTP 200.
curl -sS -X PUT "$API_URL/items/1" \
  -H "Authorization: $ID_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"id":"1","name":"Updated item"}' | jq .

# Valid DELETE: expect HTTP 200.
curl -sS -X DELETE "$API_URL/items/1" \
  -H "Authorization: $ID_TOKEN" | jq .
```

Authorized responses contain `"mock": true` and request details. The backend
is stateless: writes are simulated and GET always returns fixed sample data.

To inspect HTTP status and headers instead of pretty-printing the JSON body:

```sh
curl -i "$API_URL/items"
curl -i "$API_URL/items" -H "Authorization: $ID_TOKEN"
```

## How the configuration works

- `cognito.tf` creates the user directory and an app client supporting password
  sign-in. An app client identifies the application requesting tokens.
- The OpenAPI global security rule protects all four item operations with the
  built-in `cognito_user_pools` authorizer. The scope list is empty intentionally
  because this example uses ID tokens for identity verification.
- The audience validation expression binds accepted ID tokens to this app
  client. Keep `YOUR_CLIENT_ID`, `YOUR_USER_POOL_ARN`, and
  `YOUR_BACKEND_INVOKE_ARN` in the source YAML; Terraform fills them in memory.
- API Gateway's Cognito authorizer is not a Lambda function. There is no
  authorizer ZIP, execution role, or shared `AUTH_TOKEN` environment variable.
- The only Lambda is the backend. Its execution role permits writing to its own
  log group; Cognito validates the user's password, and API Gateway validates
  the token before invoking the backend.
- REST API deployment snapshots are replaced when the rendered YAML changes.
  This project has no CORS preflight or browser login flow.

This demonstrates identity authentication. Every authenticated user of this
client can invoke every item route; it does not implement user-specific data
ownership or role-based access rules. Access-token authorization with custom
OAuth scopes requires a different scope and sign-in-flow configuration.

## Local checks and troubleshooting

From this project's root:

```sh
python3 -m unittest discover -s tests -v
```

These tests check the helper's behavior and secret handling. They do not
simulate or prove Cognito's cryptographic validation; use the deployed curl
checks for that.

- **Expired SSO token:** repeat `aws sso login --profile sandbox` for admin or
  Terraform operations. This is separate from a user's Cognito login.
- **AccessDenied on CreateRole:** add the scoped IAM permissions for this
  project's role, then generate a new Terraform plan.
- **NotAuthorizedException on login:** confirm the username, password, region,
  and client ID. The helper reports an error code without printing raw input.
- **Unexpected login challenge:** ensure the user has a permanent password.
- **401 with a token:** obtain a fresh ID token from this project's client.
  Do not use another project's shared token or an access token in its place.
- **500 from the API:** inspect the backend CloudWatch log group, available
  through `terraform output -raw lambda_log_group`.

## Cleanup

From this project's `terraform/` directory:

```sh
terraform plan -destroy
terraform destroy
unset ID_TOKEN USER_POOL_ID CLIENT_ID API_URL TEST_USERNAME
```

Confirm the deletion. Destroy removes the user pool **and its users**, app
client, REST API/stage/deployment, backend Lambda, execution role/policy, and
log group. Keep the local state until cleanup succeeds. Other projects are
independent.

Commit configuration, source, examples, documentation, tests, and the provider
lock file. Local state, saved plans, variable settings, providers, and ZIPs are
ignored. Do not add token or password files to the repository.

References: [Cognito authorizers for REST APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-enable-cognito-user-pool.html),
[Cognito InitiateAuth](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_InitiateAuth.html),
and [Terraform Cognito app client](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cognito_user_pool_client).
