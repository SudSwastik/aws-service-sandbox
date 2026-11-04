variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefix for new resources. Use a name distinct from manually created resources."
  type        = string
  default     = "items-api"

  validation {
    condition     = can(regex("^[a-zA-Z0-9_-]{1,48}$", var.project_name))
    error_message = "Use 1–48 letters, numbers, hyphens, or underscores."
  }
}

variable "existing_lambda_role_arn" {
  description = "Optional existing Lambda execution role ARN. When set, Terraform creates no IAM role or role policy. The role must trust Lambda and already allow writing to this function's log group."
  type        = string
  default     = null

  validation {
    condition     = var.existing_lambda_role_arn == null || can(regex("^arn:[^:]+:iam::[0-9]{12}:role/.+$", var.existing_lambda_role_arn))
    error_message = "Supply a full IAM role ARN, or leave this variable unset."
  }
}
