# Deploy the mock API with Terraform

Terraform creates and manages AWS resources from configuration files. Instead
of clicking through the console, you describe the desired setup in `.tf` files.
Terraform calls AWS APIs to create it and records which resources it manages.

This directory creates a new Lambda and HTTP API using the existing
`../lambda/lambda_function.py` and `../api-gateway/openapi.yaml`. You do not need to upload code, edit the OpenAPI
placeholders, or attach routes manually for this deployment.

## What happens when you call the API?

```text
curl → API Gateway route → Lambda proxy integration → Python handler
     ← JSON response    ←                          ← mock response
```

The four routes are `GET /items`, `POST /items`, `PUT /items/{id}`, and
`DELETE /items/{id}`. All use the same Lambda. The `$default` stage publishes
the routes at the API base URL, without a `/dev` suffix.

This setup has a public endpoint with no authentication. It returns mock data
and echoes request details without storing changes. API requests, Lambda
invocations, and CloudWatch logs can incur AWS charges; delete the setup when
finished. No VPC, database, or S3 bucket is created.

## The terms you need

| Term | Meaning in this project |
| --- | --- |
| Configuration | The `.tf` files describing the resources you want |
| Provider | A plugin that lets Terraform work with a service; `aws` talks to AWS and `archive` creates the ZIP |
| Resource | Something Terraform manages, such as a Lambda or an API route |
| Data source | Reads or computes information; here it reads the account ID and packages the code |
| Variable | An input you can change, such as the region |
| Output | A useful result printed after deployment, such as the API URL |
| State | Terraform's local record mapping its resource names to real AWS resources |
| Plan | A preview of the changes Terraform intends to make |
| Apply | The command that makes the planned AWS changes |

## 1. Install the tools

You need Terraform, AWS CLI v2, curl, and jq. On macOS with Homebrew installed:

```sh
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
brew install awscli jq

terraform version
aws --version
jq --version
```

If you already have a tool, skip its installation command.
For other systems, use [HashiCorp's installation instructions](https://developer.hashicorp.com/terraform/install).
Terraform runs on your computer; it does not need to be installed inside Lambda.

## 2. Select your AWS account

Terraform uses your AWS credentials, just like the AWS CLI. Use a sandbox
profile that has already been configured. For an IAM Identity Center/SSO profile:

```sh
# Only needed if you have not configured this SSO profile before:
aws configure sso --profile sandbox

aws sso login --profile sandbox
export AWS_PROFILE=sandbox
aws sts get-caller-identity
```

Replace `sandbox` with your actual profile name. If your profile uses a
different authentication method, use its normal sign-in process instead of the
SSO commands. Confirm the displayed `Account` is the account you intend to use.
Do not put access keys into `.tf` files.

The identity running Terraform needs permission to manage Lambda functions,
HTTP APIs and their routes/integrations/stages, CloudWatch log groups, IAM roles
and inline policies, and Lambda invocation permissions. It also needs
`iam:PassRole` for the execution role and permission to tag these resources.
The Lambda execution role is a separate identity with only log-writing access.
If your account restricts these actions, an account administrator must grant the
appropriate sandbox permissions.

If you reuse an existing execution role as described below, provisioning does
not create or modify IAM roles or their policies. `iam:PassRole` is still required.

## 3. Choose names and region

From the repository root:

```sh
cd api-gateway-lambda-passthrough/terraform
cp -n terraform.example.tfvars terraform.tfvars
```

Edit `terraform.tfvars`:

```hcl
aws_region   = "us-east-1"
project_name = "items-api"
```

The region determines where the resources are created. The project name becomes
the Lambda and API name, and prefixes the IAM role name. Use a different name
if those names already exist. IAM role names are account-wide.

This creates new resources. Terraform does not automatically adopt the Lambda
and API you created in the console. Existing resources remain separate and
continue to exist after this Terraform setup is destroyed. Managing them with
Terraform would require a separate import and configuration reconciliation.

## 4. Initialize and check

### If deployment fails with `iam:CreateRole` / PowerUserAccess

The default configuration creates an execution role. A deployment identity with
only AWS's `PowerUserAccess` policy cannot do that. Terraform cannot grant itself
the missing permissions.

For the default Terraform-managed role, an administrator can add the statements
from [the example deployment policy](iam/deployment-policy.example.json) to your
SSO permission set's inline policy, in addition to `PowerUserAccess`. Replace
`YOUR_ACCOUNT_ID` with your account ID and adjust `items-api-role` if you changed
`project_name`. The example supplies IAM permissions only, not the Lambda,
API Gateway, and CloudWatch permissions already supplied by `PowerUserAccess`.
Save the permission set, provision it to the target account, and refresh your
SSO login. Keep `existing_lambda_role_arn` unset for this option. Permission set
updates apply to everyone assigned to that permission set.

Alternatively, ask your administrator to provide a Lambda execution role in the same
account. It must trust `lambda.amazonaws.com` with `sts:AssumeRole` and permit
`logs:CreateLogStream` and `logs:PutLogEvents` under
`/aws/lambda/items-api` (adjust for your project name). Your existing manually
created Lambda's role is also an option if its permissions cover the new log group.

Find an existing function's execution role in **Lambda → function → Configuration
→ Permissions → Execution role**, or use:

```sh
aws lambda get-function-configuration \
  --function-name YOUR_EXISTING_FUNCTION \
  --region us-east-1 --query Role --output text
```

Append its full ARN to your local `terraform.tfvars`, replacing the example:

```hcl
existing_lambda_role_arn = "arn:aws:iam::123456789012:role/items-api-execution-role"
```

Terraform then skips IAM role and inline policy creation. It does not modify
or delete that externally managed role. Have your administrator grant the
deployment identity `iam:PassRole` for that specific role, restricted to Lambda.
For an SSO profile, the administrator manages this in your assigned IAM Identity
Center permission set. A scoped policy statement looks like this (replace ARN):

```json
{
  "Effect": "Allow",
  "Action": "iam:PassRole",
  "Resource": "arn:aws:iam::123456789012:role/items-api-execution-role",
  "Condition": {
    "StringEquals": {"iam:PassedToService": "lambda.amazonaws.com"}
  }
}
```

After the permission update, refresh your SSO login. Regenerate any saved plan
and apply again. Keep the current state file: a failed apply may have already
created the log group, which Terraform will reuse on the next run.

If the setup already has a Terraform-created role in use, review the plan
carefully before switching modes; removing that managed role from configuration
can schedule its deletion. Role reuse is intended here for the failed initial
deployment where IAM role creation never succeeded.

References: [PowerUserAccess policy](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/PowerUserAccess.html)
and [Lambda PassRole troubleshooting](https://docs.aws.amazon.com/lambda/latest/dg/security_iam_troubleshoot.html).

### Initialize and preview

Run all remaining Terraform commands from this directory:

```sh
terraform init
terraform fmt
terraform validate
terraform plan -out=deployment.tfplan
```

- `init` downloads the AWS and archive providers into `.terraform/` and creates
  `.terraform.lock.hcl`, which records the selected provider versions.
- `fmt` formats the `.tf` files consistently.
- `validate` checks the configuration against the providers' schemas. It does
  not prove that your AWS credentials have permission to deploy.
- `plan` reads AWS information and previews changes. It does not create AWS
  resources, though the archive data source can write the local ZIP file.

In a plan, `+` means create, `~` means update, and `-` means delete. Some IDs and
URLs show as `(known after apply)` because AWS has not created them yet. Review
the resource names and actions before continuing.

## 5. Deploy

```sh
terraform apply deployment.tfplan
```

This applies the saved plan from step 4 without another confirmation prompt,
so review the plan before running it. This changes AWS and can incur charges.
If you edit the configuration or inputs, generate a new saved plan first.
Alternatively, `terraform apply` without a saved plan previews fresh changes
and asks you to type `yes` before applying them.

Terraform works out creation order from references between resources. For
example, the API definition references the Lambda name, so Terraform creates
the Lambda before importing the API definition. You do not need to create each resource by hand.

After it finishes, Terraform prints `api_url`, `lambda_function_name`,
`lambda_log_group`, and `aws_region`. You can retrieve them later with
`terraform output`.

## 6. Test with curl and jq

While still in this directory:

```sh
export API_URL="$(terraform output -raw api_url)"

# GET: fixed sample items, HTTP 200
curl -sS "$API_URL/items?status=active" | jq .

# POST: echoed object with a mock ID, HTTP 201
curl -sS -X POST "$API_URL/items" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Test item","status":"active"}' | jq .

# PUT: echoed updated object, HTTP 200
curl -sS -X PUT "$API_URL/items/1" \
  -H 'Content-Type: application/json' \
  -d '{"id":"1","name":"Updated item","status":"inactive"}' | jq .

# DELETE: mock confirmation, HTTP 200
curl -sS -X DELETE "$API_URL/items/1" | jq .
```

Check the response's `request` field to see the method, path, query parameters,
and JSON body received by Lambda. GET always returns the same mock data, even
after POST, PUT, or DELETE.

To see HTTP headers and the status code instead of pretty-printing JSON:

```sh
curl -i "$API_URL/items"
```

To follow Lambda invocation logs:

```sh
aws logs tail "$(terraform output -raw lambda_log_group)" \
  --region "$(terraform output -raw aws_region)" \
  --since 10m --follow
```

Press Ctrl-C to stop following logs. The handler does not explicitly log request
bodies; Lambda's platform logs help identify invocation errors.

## How the configuration connects everything

| File | What to look for |
| --- | --- |
| `versions.tf` | Terraform/provider version constraints, AWS region, and resource tags |
| `variables.tf` | Region and project name inputs, including name validation |
| `main.tf` | The resources and their connections |
| `outputs.tf` | API URL, Lambda name, and log group outputs |
| `terraform.example.tfvars` | Example input values to copy to your local `terraform.tfvars` |

In `main.tf`:

1. `archive_file.lambda` zips only `lambda_function.py`. Lambda uses
   `lambda_function.lambda_handler`: the first part is the filename without
   `.py`, and the second is the Python function name.
2. `aws_iam_role.lambda` allows Lambda to assume its execution role.
   `aws_iam_role_policy.logs` lets that role write to the experiment's log group.
   Both are skipped when `existing_lambda_role_arn` is set; that role's owner
   maintains its trust and logging permissions.
3. `aws_lambda_function.mock` uploads the ZIP and uses Python 3.13. The source
   hash tells Terraform when the handler has changed.
4. `aws_apigatewayv2_api.mock` creates an HTTP API. The provider resource name
   uses `v2` for HTTP APIs; it does not mean your API must be named version 2.
5. `local.openapi_body` reads `../api-gateway/openapi.yaml` and replaces `YOUR_REGION`,
   `YOUR_ACCOUNT_ID`, and `YOUR_FUNCTION_NAME` in memory with deployment values.
   The original YAML is not changed. Keep those placeholders in the source YAML
   when using Terraform so it can connect the new Lambda automatically.
6. The API's `body` argument imports that definition. `yamldecode` reads YAML as
   structured data, and `jsonencode` serializes it for the API import. Routes and
   proxy integrations come from the YAML; there are no separate Terraform route
   or integration resources. The integration's `httpMethod: POST` is the internal
   Lambda invocation method; clients still use the four configured HTTP methods.
7. `aws_lambda_permission.api_gateway` lets this API invoke the function for
   item paths. Importing integrations and allowing invocation are separate
   steps; Terraform handles both.
8. `aws_apigatewayv2_stage.default` enables automatic deployment of API changes.
   You do not click Deploy after each Terraform change.

To add or change a route, edit `../api-gateway/openapi.yaml`, then run `terraform plan` and
`terraform apply`. The invocation permission currently covers `/items` paths;
if you add other path prefixes, update its scope accordingly.

## Updates and state

To change the handler, edit `../lambda/lambda_function.py`, then run `terraform plan`
and `terraform apply` again. Terraform updates the function when its ZIP hash
changes. Running apply without changes should report no changes.

Terraform writes local `terraform.tfstate` and may write a backup. Keep them
safe: they track your deployed resources and can contain sensitive information.
They are ignored by Git. Deleting state does not delete AWS resources and can
make Terraform lose track of them. Use the same state directory for updates and
cleanup. For a shared team setup, configure a remote backend before sharing
management of these resources.

Commit the `.tf` files, example variables, and generated `.terraform.lock.hcl`.
Do not commit `.terraform/`, state, local `terraform.tfvars`, or `lambda.zip`.
Avoid console edits to Terraform-managed resources; review the next plan if
you make one, because Terraform may restore the configured values.

## 7. Remove the test setup

```sh
terraform plan -destroy
terraform destroy
```

Review the deletion plan and type `yes` at the destroy prompt. Terraform deletes
the resources managed by this state, including the log group and its logs.
Your earlier manually created API and Lambda are not part of this state and
must be cleaned up separately if you no longer need them.

## Common errors

- **Credentials not found / expired token:** select the right `AWS_PROFILE`,
  sign in again if needed, and check `aws sts get-caller-identity`.
- **AccessDenied:** inspect the failed action; the identity running Terraform
  may lack provisioning permissions or `iam:PassRole`. For `iam:CreateRole`,
  see the existing execution role option in step 4.
- **Resource already exists:** choose a new project name rather than trying
  to reuse a console-created Lambda or role without importing it.
- **Not Found:** use the Terraform output URL with `/items`. This deployment
  has no `/dev` prefix and no route for `/`.
- **Internal Server Error:** check the Lambda log group and the function's
  handler configuration. Confirm `terraform apply` finished successfully.

The overall approach follows [HashiCorp's Lambda and API Gateway tutorial](https://developer.hashicorp.com/terraform/tutorials/aws/lambda-api-gateway)
and the [AWS Lambda proxy integration documentation](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-lambda.html).
