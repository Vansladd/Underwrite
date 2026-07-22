terraform {
  required_version = "~> 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Region duplicated from var.region: backend blocks cannot use variables. See DECISIONS D-013.
  backend "s3" {
    bucket       = "underwrite-tfstate"
    key          = "prod/terraform.tfstate"
    region       = "eu-west-2"
    encrypt      = true
    use_lockfile = true
  }
}
