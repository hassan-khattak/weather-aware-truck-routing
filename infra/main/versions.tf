terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # The bucket name is passed at init time:
  #   terraform init -backend-config="bucket=<state bucket>"
  backend "s3" {
    key          = "truckroute/main.tfstate"
    region       = "us-east-1"
    use_lockfile = true
    encrypt      = true
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { project = "weather-aware-truck-routing" }
  }
}

# CloudWatch billing metrics only exist in us-east-1.
provider "aws" {
  alias  = "billing"
  region = "us-east-1"
  default_tags {
    tags = { project = "weather-aware-truck-routing" }
  }
}
