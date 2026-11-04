# AWS Service Sandbox

A workspace for experimenting with Amazon API Gateway, AWS Lambda, and
integrations with other AWS services.

Use this repository to build small test setups, explore service behavior, and
verify integrations. No runtime, framework, or infrastructure tool has been
selected yet.

## Experiment layout

Keep each experiment in its own directory, with the code, infrastructure, and
instructions needed to reproduce it. For example:

```text
api-gateway-lambda/
  README.md
  src/
  infra/
  tests/
```

This is a suggested layout; experiment directories have not been created yet.

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
