terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "argus"
      Environment = var.environment
      Stack       = "ec2-smoke"
      ManagedBy   = "terraform"
    }
  }
}
