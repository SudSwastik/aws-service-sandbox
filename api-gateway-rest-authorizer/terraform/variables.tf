variable "aws_region" {
  description = "AWS region for the REST API and both Lambda functions."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Resource name prefix, distinct from the HTTP API project."
  type        = string
  default     = "items-rest-api"

  validation {
    condition     = can(regex("^[a-zA-Z0-9_-]{1,40}$", var.project_name))
    error_message = "Use 1–40 letters, numbers, hyphens, or underscores."
  }
}

variable "stage_name" {
  description = "REST API stage included in the invoke URL."
  type        = string
  default     = "dev"

  validation {
    condition     = can(regex("^[a-zA-Z0-9_]{1,128}$", var.stage_name))
    error_message = "Use 1–128 letters, numbers, or underscores."
  }
}

variable "auth_token" {
  description = "Sandbox bearer token supplied using TF_VAR_auth_token. Stored in state and Lambda environment configuration."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.auth_token) >= 32 && can(regex("^[A-Za-z0-9_-]+$", var.auth_token))
    error_message = "Use at least 32 URL-safe letters, numbers, hyphens, or underscores."
  }
}
