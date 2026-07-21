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

variable "domain" {
  description = "Hostname Caddy requests a certificate for (UW-067)"
  type        = string
  default     = "underwrite.nexusstechnologies.com"
}
