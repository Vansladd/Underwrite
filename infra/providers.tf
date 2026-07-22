# Credentials come from AWS_PROFILE, never HCL, so CI can use OIDC unchanged.
provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = var.project
      ManagedBy = "terraform"
    }
  }
}
