variable "region" {
  type    = string
  default = "us-east-1"
}

variable "prefix" {
  type        = string
  default     = "truckroute"
  description = "Short prefix for resource names and SSM parameters."
}

variable "instance_type" {
  type    = string
  default = "t3.small"
}

variable "admin_cidr" {
  type        = string
  default     = ""
  description = "CIDR allowed to SSH (port 22), e.g. 203.0.113.7/32. Empty disables SSH; SSM Session Manager is always available."
}

variable "origin_secret" {
  type        = string
  sensitive   = true
  description = "Value of the X-Origin-Secret header CloudFront adds and Caddy verifies. Note: it is stored in Terraform state (encrypted, private bucket)."
}

variable "github_owner" {
  type        = string
  description = "GitHub user/org that owns the repository."
}

variable "github_repo" {
  type    = string
  default = "weather-aware-truck-routing"
}

variable "github_environment" {
  type    = string
  default = "production"
}

variable "create_github_oidc_provider" {
  type        = bool
  default     = true
  description = "Set false if the account already has the token.actions.githubusercontent.com OIDC provider."
}

variable "billing_alarm_usd" {
  type    = number
  default = 20
}

variable "billing_alarm_email" {
  type        = string
  description = "Email that receives the billing alarm."
}
