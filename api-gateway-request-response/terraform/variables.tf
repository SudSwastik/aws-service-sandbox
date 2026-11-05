variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project_name" {
  type    = string
  default = "request-response-api"
  validation {
    condition     = can(regex("^[a-zA-Z0-9_-]{1,40}$", var.project_name))
    error_message = "Use 1–40 letters, numbers, hyphens or underscores."
  }
}

variable "stage_name" {
  type    = string
  default = "dev"
  validation {
    condition     = can(regex("^[a-zA-Z0-9_]{1,128}$", var.stage_name))
    error_message = "Use 1–128 letters, numbers or underscores."
  }
}

variable "rate_limit" {
  description = "Target requests per second per API key."
  type        = number
  default     = 2
  validation {
    condition     = var.rate_limit > 0
    error_message = "Rate must be positive."
  }
}

variable "burst_limit" {
  type    = number
  default = 3
  validation {
    condition     = var.burst_limit >= 1 && floor(var.burst_limit) == var.burst_limit
    error_message = "Burst must be a positive integer."
  }
}

variable "daily_quota" {
  type    = number
  default = 1000
  validation {
    condition     = var.daily_quota >= 1 && floor(var.daily_quota) == var.daily_quota
    error_message = "Quota must be a positive integer."
  }
}
