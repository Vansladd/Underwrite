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
