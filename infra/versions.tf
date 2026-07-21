terraform {
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # use_lockfile is native S3 locking, GA in 1.11. A DynamoDB lock table is deprecated.
  backend "s3" {
    bucket       = "underwrite-tfstate"
    key          = "prod/terraform.tfstate"
    region       = "eu-west-2"
    encrypt      = true
    use_lockfile = true
  }
}
