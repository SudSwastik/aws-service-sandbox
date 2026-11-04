# AWS Service Sandbox

A workspace for experimenting with Amazon API Gateway, AWS Lambda, and
integrations with other AWS services.

Use this repository to build small test setups, explore service behavior, and
verify integrations. Each project chooses the runtime and infrastructure tools
appropriate to its integration.

## Project layout

Keep each integration in its own directory at the repository root. Within a
project, group files by service and keep deployment configuration together:

```text
api-gateway-lambda-passthrough/
  README.md
  lambda/
    lambda_function.py
  api-gateway/
    openapi.yaml
  terraform/
    README.md
    main.tf
    variables.tf
    outputs.tf
    versions.tf
    terraform.example.tfvars
```

The [API Gateway and Lambda project](api-gateway-lambda-passthrough/README.md)
includes a stateless mock API and a
[Terraform deployment walkthrough](api-gateway-lambda-passthrough/terraform/README.md).
Use the same grouping for future projects, adding service folders as needed.

## Getting started

1. Create a directory for the integration you want to test.
2. Document its runtime, tooling, AWS permissions, and other prerequisites.
3. Configure an AWS profile and region for the target sandbox account.
4. Add setup, deployment, invocation, verification, and cleanup instructions.

For experiments using the AWS CLI, select your profile and region and verify
the target account before deploying:

```sh
export AWS_PROFILE=your-sandbox-profile
export AWS_REGION=us-east-1
aws sts get-caller-identity
```

Use your intended region in place of the example. Each experiment should state
whether verification runs locally, against mocks, or against deployed AWS
resources.

## AWS resources and credentials

- Use profiles, environment variables, or IAM roles for authentication.
- Keep credentials, secrets, and sensitive test data out of version control.
- Make account-specific values and resource names configurable.
- Scope permissions and resource changes to the experiment.
- Document resources that incur charges and remove them when testing ends.
- Ensure cleanup targets only resources created for that experiment.
