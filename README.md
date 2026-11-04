# AWS Service Sandbox

A collection of small projects for exploring AWS services, testing APIs, and
validating integrations.

## Structure

Each project lives in its own directory at the repository root. Group source
code and configuration by service, with deployment files kept together.

```text
<project-name>/
  README.md
  <service-name>/
  terraform/          # When using Terraform
```

## Getting started

Open a project's README for its prerequisites, configuration, deployment,
testing, and cleanup instructions. Tooling and runtimes may vary by project.

When adding a project, include reproducible setup steps, example requests,
expected results, and commands to remove its resources.

## Configuration and cleanup

Use AWS profiles or IAM roles for authentication. Keep credentials, local
settings, Terraform state, and generated artifacts out of version control.
Make account-specific values and regions configurable.

Deploy to the intended AWS account and region. Test resources can incur
charges; remove them when finished.
