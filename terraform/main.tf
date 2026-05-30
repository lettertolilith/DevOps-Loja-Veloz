# =============================================================================
# Loja Veloz — Infraestrutura como Código (IaC) com Terraform
# Esqueleto: VPC + EKS Cluster + Node Group
# Justificativa: declarar a infra em Git permite criar/destruir ambientes
# (dev/staging/prod) de forma reproduzível e auditável. State remoto no S3
# com lock no DynamoDB evita corrupção em times.
# =============================================================================

terraform {
  required_version = ">= 1.6"

  required_providers {
    aws        = { source = "hashicorp/aws",        version = "~> 5.60" }
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.30" }
    helm       = { source = "hashicorp/helm",       version = "~> 2.14" }
  }

  # Remote state — descomente após criar bucket e tabela
  # backend "s3" {
  #   bucket         = "loja-veloz-tfstate"
  #   key            = "envs/dev/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "loja-veloz-tflock"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "loja-veloz"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# --- VPC ---
module "vpc" {
  source = "./modules/vpc"

  name        = "loja-veloz-${var.environment}"
  cidr        = "10.0.0.0/16"
  azs         = ["us-east-1a", "us-east-1b", "us-east-1c"]
  environment = var.environment
}

# --- EKS Cluster ---
module "eks" {
  source = "./modules/eks"

  cluster_name    = "loja-veloz-${var.environment}"
  cluster_version = "1.30"
  vpc_id          = module.vpc.vpc_id
  subnet_ids      = module.vpc.private_subnet_ids

  node_groups = {
    general = {
      desired_size = var.environment == "prod" ? 3 : 2
      min_size     = var.environment == "prod" ? 3 : 1
      max_size     = var.environment == "prod" ? 10 : 4
      instance_types = ["t3.medium"]
      capacity_type  = "ON_DEMAND"
    }
  }

  environment = var.environment
}

# --- Outputs úteis ---
output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "cluster_name" {
  value = module.eks.cluster_name
}
