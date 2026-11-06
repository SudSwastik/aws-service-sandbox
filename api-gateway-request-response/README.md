# REST API request and response testing

An independent API Gateway REST API project for inspecting requests, changing
request/response data in API Gateway, validating JSON, and testing API keys,
usage quotas and throttling. Terraform deploys a Regional REST API and one Python
Lambda. Routes and mapping templates live in [openapi.yaml](api-gateway/openapi.yaml).

This project uses API keys for usage tracking. It has no Cognito or Lambda
authorizer. An API key is not user authentication; add an authorizer when testing
identity protection. Requests and writes are simulated, with no database.

## Routes and expected behavior

All routes except health and OPTIONS require `x-api-key`.

| Route | Integration | What to test |
| --- | --- | --- |
| `GET /health` | Gateway mock | Public health response without invoking Lambda |
| `GET /inspect` | Lambda proxy | Headers, query values and repeated query parameters |
| `POST /inspect` | Lambda proxy | JSON, text and base64-decoded incoming body |
| `POST /orders` | Lambda custom | Request/body transformation, JSON validation, HTTP 201 |
| `GET /orders/{orderId}` | Lambda custom | Path extraction, required header, query defaults |
| `PUT /orders/{orderId}` | Lambda custom | Validated update body, HTTP 200 |
| `DELETE /orders/{orderId}` | Lambda custom | Custom path and method handling |
| `ANY /files/{proxy+}` | Lambda proxy | Arbitrarily nested paths and HTTP methods |
| `GET /status/{code}` | Lambda proxy | 200, 201, 400, 404, 422 or 500; other codes return 400 |
| `OPTIONS` on each resource | Gateway mock | Public CORS preflight |

The backend returns only selected headers (`content-type`, `x-client-name`,
`x-trace-id`). API keys, Authorization and cookies are excluded from responses.
Do not put secrets in test query strings or bodies: those are intentionally echoed.

## What transformations do

Proxy integrations let Lambda read the REST proxy event and choose the HTTP
response. Custom integrations use VTL (Velocity Template Language) scripts in
API Gateway before and after invoking Lambda.

For `/orders` and `/orders/{orderId}`:

1. API Gateway requires a nonempty `x-client-name` header. POST/PUT JSON requires
   `name` (nonempty string) and `quantity` (integer at least 1), with no other fields.
2. The request template selects `x-client-name`, renames it to `headers.clientName`,
   and adds `headers.gatewayAdded`. It extracts `orderId`, uppercases `currency`
   (default `USD`), and wraps JSON under `body.payload` with `body.source` added.
3. Lambda receives this constructed JSON event. A Lambda invocation has no HTTP
   query/header transport: these changes are fields in the event sent to Lambda.
4. Lambda returns data containing `httpStatus`, `backendVersion` and `internalDebug`.
5. The response template wraps selected data with `gatewayTransformed`, drops the
   internal fields, and overrides the HTTP status from `httpStatus`.
6. Response parameter mappings add `X-Response-Source: api-gateway-mapping`, map
   `backendVersion` into `X-Backend-Version`, and add a CORS origin header.

Add `?reject=true` to a mapped route to get HTTP 422. This is a business rejection,
not a Lambda exception. Request validation failures return 400 before Lambda.
Unsupported content types on custom integrations return 415. Proxy routes can
accept text. Header/query presence validation does not validate their types or
format. Actual HTTP backend URL/header rewrites would require an HTTP integration.

CORS allows `*` without cookies/credentials. Preflight allows the demonstrated
GET/POST/PUT/DELETE methods and named headers. It is not an authentication feature.

## Prerequisites and permissions

Install Terraform >=1.5 and <2.0, AWS CLI v2, Python 3, curl and jq.

For an SSO identity with PowerUserAccess, merge the statements from
[deployment-policy.example.json](terraform/iam/deployment-policy.example.json)
into your permission set's existing inline policy. Replace `YOUR_ACCOUNT_ID`.
These allow management of `request-response-api-role` and passing it to Lambda.
If changing `project_name`, change the role name in the policy too. Provision
permission-set changes to your account. Other required permissions (API Gateway,
Lambda, CloudWatch and tags) must already be granted by your deployment identity.
Terraform creates the role; do not create it manually.

## Deploy

From the repository root, use your actual profile name in place of `sandbox`:

```sh
export AWS_PROFILE=sandbox
aws sso login --profile "$AWS_PROFILE"
aws sts get-caller-identity
cd api-gateway-request-response/terraform
cp -n terraform.example.tfvars terraform.tfvars
```

Review `terraform.tfvars`. Defaults are project `request-response-api`, region
`us-east-1`, stage `dev`, 2 requests/second, burst capacity 3, and 1,000 requests/day
per API key. The API-wide method throttle targets 50 requests/second, burst 100.
A burst is token-bucket capacity, not a daily quota. These resources can incur charges.

Run commands separately, continuing only when each succeeds:

```sh
terraform init
terraform fmt -check
terraform validate
terraform plan -out=deployment.tfplan
```

Review the plan, then deploy it (the saved plan applies without another prompt):

```sh
terraform apply deployment.tfplan
```

In the same Terraform directory, load configuration without printing the key:

```sh
export API_URL="$(terraform output -raw api_url)"
export API_KEY="$(terraform output -raw api_key)"
test -n "$API_URL" && test -n "$API_KEY" && echo "Configuration loaded"
```

The URL already includes `/dev`. AWS generates the API key; it is a sensitive
Terraform output, but is still present in local Terraform state and saved plans.
Those files are ignored and must remain private. Do not commit or print the key.
Usage-plan/key changes can take a few minutes to propagate; wait before testing
if an otherwise correct newly deployed key initially receives 403.

## Manual tests with curl and jq

Run tests individually: fast consecutive requests can hit the deliberately low
rate limit. If you get 429, wait for the bucket to refill before retrying.

Public health (200), missing key (403), and invalid key (403):

```sh
curl -sS "$API_URL/health" | jq .
curl -sS "$API_URL/inspect" | jq .
curl -sS "$API_URL/inspect" -H 'x-api-key: invalid' | jq .
```

Inspect headers, repeated query parameters and a JSON body:

```sh
curl -sS "$API_URL/inspect?tag=one&tag=two&search=hello%20world" \
  -H "x-api-key: $API_KEY" -H 'x-client-name: terminal' \
  -H 'x-trace-id: trace-123' | jq .

curl -sS -X POST "$API_URL/inspect" \
  -H "x-api-key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{"hello":"world","nested":{"enabled":true}}' | jq .

curl -sS -X POST "$API_URL/inspect" \
  -H "x-api-key: $API_KEY" -H 'Content-Type: text/plain' \
  --data-binary 'Plain text body' | jq .
```

Create an order (201): `eur` becomes `EUR`, the header becomes `clientName`,
and your body moves under `data.body.payload`:

```sh
curl -sS -X POST "$API_URL/orders?currency=eur" \
  -H "x-api-key: $API_KEY" -H 'x-client-name: terminal' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Book","quantity":2}' | jq .
```

Inspect the modified response headers with `-i` (do not pipe headers to jq):

```sh
curl -i "$API_URL/orders/42" \
  -H "x-api-key: $API_KEY" -H 'x-client-name: terminal'
```

Read, update, delete and return a business rejection:

```sh
curl -sS "$API_URL/orders/42?currency=gbp" \
  -H "x-api-key: $API_KEY" -H 'x-client-name: terminal' | jq .

curl -sS -X PUT "$API_URL/orders/42" \
  -H "x-api-key: $API_KEY" -H 'x-client-name: terminal' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Updated book","quantity":3}' | jq .

curl -sS -X DELETE "$API_URL/orders/42" \
  -H "x-api-key: $API_KEY" -H 'x-client-name: terminal' | jq .

curl -sS "$API_URL/orders/42?reject=true" \
  -H "x-api-key: $API_KEY" -H 'x-client-name: terminal' | jq .
```

Missing required header (400), invalid JSON schema (400), unsupported content type
(415), custom response status (404), and nested path (200):

```sh
curl -sS "$API_URL/orders/42" -H "x-api-key: $API_KEY" | jq .

curl -sS -X POST "$API_URL/orders" \
  -H "x-api-key: $API_KEY" -H 'x-client-name: terminal' \
  -H 'Content-Type: application/json' -d '{"quantity":0}' | jq .

curl -sS -X POST "$API_URL/orders" \
  -H "x-api-key: $API_KEY" -H 'x-client-name: terminal' \
  -H 'Content-Type: text/plain' -d 'hello' | jq .

curl -sS "$API_URL/status/404" -H "x-api-key: $API_KEY" | jq .

curl -sS "$API_URL/files/reports/2026/report.json?download=true" \
  -H "x-api-key: $API_KEY" | jq .
```

Public browser preflight:

```sh
curl -i -X OPTIONS "$API_URL/orders" \
  -H 'Origin: https://example.com' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-api-key,x-client-name'
```

## Automated deployed tests and throttling

From `terraform/`, with `API_URL` and `API_KEY` loaded:

```sh
python3 ../scripts/test_api.py
python3 ../scripts/test_api.py --rate
```

The first command checks statuses and transformation results with paced requests.
The second repeats these checks then sends 40 requests with at most 10 concurrent
workers and prints status counts and elapsed time. Unexpected statuses other than
200 and 429 fail the burst test. With default limits, expect a mixture of 200
and 429. The burst consumes your daily quota. AWS usage-plan throttling and quotas
are **best effort**, so exact counts and strict ceilings are not guaranteed.
They are not a spending cap. Different API keys get separate usage counters;
clients sharing this key share the same allowance.

### Verified deployment results

The deployed test run passed all 15 functional checks, including request and
response transformations, validation, API-key rejection and public OPTIONS
preflight after applying the repair below. Its 40-request burst returned 38 HTTP
200 responses and 2 HTTP 429 responses. These counts are one observed run, not
expected counts for future runs or proof of a strict two-requests-per-second
ceiling. The daily quota was configured but exhaustion was not verified by this run.

For quota testing, optionally lower `daily_quota` to 20 in your ignored
`terraform.tfvars`, plan/apply again, and send paced requests until you get 429.
A response body of `QUOTA_EXCEEDED` distinguishes quota exhaustion from
`THROTTLED`. Usage already recorded for the key counts toward its quota. Restore
the value and apply when done; propagation can take time. Requests may exceed the
target quota because enforcement is best effort.

## Change or add custom routes

Edit `api-gateway/openapi.yaml`. Copy an operation with its integration and,
for path parameters, declare them as required. Keep
`YOUR_BACKEND_INVOKE_ARN` unchanged; Terraform fills it in memory. Add public
`security: []` only to intentionally public operations. Add OPTIONS when browser
clients need preflight and update allowed methods/headers if necessary.

Re-plan and apply from `terraform/`; the deployment hash creates a new API
snapshot when the rendered YAML changes. The Lambda package hash also updates
Lambda when its source changes. Do not manually create routes in the console
alongside this YAML: Terraform imports it using overwrite mode.

## Local checks, troubleshooting and cleanup

From this project's root:

```sh
python3 -m unittest discover -s tests -v
terraform -chdir=terraform fmt -check
```

Unit tests verify backend behavior; they cannot execute AWS VTL. The deployed
script verifies the actual gateway transformations. A live test is necessary.

- Empty `API_URL`: run `terraform output` and `terraform state list` in this
  project's Terraform directory. An empty state has no saved deployment outputs;
  locate the original state if previously deployed before applying again.
- DNS failure: check the URL, region and deployed stage, then your DNS/VPN/network.
  Authentication cannot cause hostname lookup failure.
- 403: check the API key, stage and usage-plan association/propagation. An unknown
  route can also return 403 with API Gateway's default Missing Authentication Token.
- OPTIONS returning 403: protected operations declare their own API-key requirement;
  OPTIONS must remain public with `security: []`. Apply a new Terraform plan after
  updating the YAML so the stage receives a new deployment. Browser preflights
  send Origin and Access-Control-Request headers but do not send the API key itself.
  If the response still says `INVALID_API_KEY`, explicitly clear the deployed
  OPTIONS flags using the repair steps below.
- 400: mapped routes require `x-client-name` and valid POST/PUT JSON.
- 415: use `Content-Type: application/json` on mapped routes.
- 429: pause, or check the daily usage quota. Parallel traffic with the same key
  affects your test allowance.
- 500: inspect Lambda CloudWatch logs and mapping configuration. Lambda logs are
  retained for seven days. API payload tracing is disabled.
- SSO expired: repeat `aws sso login --profile "$AWS_PROFILE"` before Terraform.

### Repair an OPTIONS method that still requires an API key

From `terraform/`, with your AWS deployment profile logged in:

```sh
export API_URL="$(terraform output -raw api_url)"
python3 ../scripts/repair_preflight.py
terraform plan -replace=aws_api_gateway_deployment.api -out=deployment.tfplan
```

The repair calls AWS `UpdateMethod` only for OPTIONS methods on the API identified
by `API_URL`, setting `apiKeyRequired=false`. It does not alter protected business
methods or read any API key values. It updates the method configuration directly;
it is a one-time repair for an incorrectly deployed flag, not a Terraform provider.
Review the plan, then publish a fresh snapshot using Terraform so its stage and
deployment state remain tracked:

```sh
terraform apply deployment.tfplan
python3 ../scripts/test_api.py
python3 ../scripts/test_api.py --rate
```

Do not supply an API key on preflight to work around this error: browsers do not
send its value on preflight. The YAML remains the intended configuration; if a
future import reintroduces the flag, inspect the deployed method before repairing.

Remove this project's resources from `terraform/`:

```sh
terraform destroy
unset API_KEY API_URL
```

Keep local state until deletion succeeds. This project has separate state and
resource names from the Cognito and Lambda-authorizer projects. No AWS resources
are deployed merely by adding these source files.

Commit source, YAML, docs, example variables and `.terraform.lock.hcl`. State,
real `.tfvars`, plans, provider directories and ZIP packages are ignored.

References: [AWS data transformations](https://docs.aws.amazon.com/apigateway/latest/developerguide/rest-api-data-transformations.html),
[AWS mapping template variables](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-mapping-template-reference.html),
[AWS usage plans](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-api-usage-plans.html).
