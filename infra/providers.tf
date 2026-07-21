# No profile here: credentials come from AWS_PROFILE, so the same config works unchanged
# when CI authenticates through GitHub OIDC.
provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = var.project
      ManagedBy = "terraform"
    }
  }
}
