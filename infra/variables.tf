variable "project" {
  description = "Name prefix and tag applied to every resource"
  type        = string
  default     = "underwrite"
}

variable "region" {
  description = "AWS region for all resources"
  type        = string
  default     = "eu-west-2"
}

# No default: a clone inheriting someone else's hostname fails issuance at #17.
variable "domain" {
  description = "Hostname Caddy requests a certificate for (UW-067)"
  type        = string
}

# No default, for the same reason as domain: this is an environment value, not the repo's.
variable "alert_email" {
  description = "Where budget notifications go"
  type        = string
}

variable "github_owner" {
  description = "GitHub org/user allowed to assume the CI role via OIDC"
  type        = string
  default     = "Vansladd"
}

variable "github_repo" {
  description = "GitHub repo (without owner) allowed to assume the CI role via OIDC"
  type        = string
  default     = "Underwrite"
}

variable "image_tag" {
  description = "pdf-render image tag to deploy; empty means the Lambda is not created (see #21)"
  type        = string
  default     = ""
}

variable "compose_plugin_version" {
  description = "docker compose plugin version installed on the instance (no leading v)"
  type        = string
  default     = "2.31.0"
}

# force_destroy on the bucket and ECR repo. Off, so terraform destroy refuses while objects
# exist; a deliberate -var allow_destroy=true enables teardown of this demo.
variable "allow_destroy" {
  description = "Allow terraform destroy to remove non-empty buckets and repositories"
  type        = bool
  default     = false
}
