variable "aws_region" {
  description = "AWS region for the API, Cognito user pool, and Lambda."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Name prefix for this independent Cognito integration."
  type        = string
  default     = "items-cognito-api"

  validation {
    condition     = can(regex("^[a-zA-Z0-9_-]{1,40}$", var.project_name))
    error_message = "Use 1–40 letters, numbers, hyphens, or underscores."
  }
}

variable "stage_name" {
  description = "REST API stage included in the base URL."
  type        = string
  default     = "dev"

  validation {
    condition     = can(regex("^[a-zA-Z0-9_]{1,128}$", var.stage_name))
    error_message = "Use 1–128 letters, numbers, or underscores."
  }
}
