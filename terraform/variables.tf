variable "region" {
  description = "Região AWS"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Ambiente alvo (dev | staging | prod)"
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment deve ser: dev, staging ou prod."
  }
}

variable "github_repo" {
  description = "lettertolilith/DevOps-Loja-Veloz"
  type        = string
}
