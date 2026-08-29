variable "aws_region" {
  description = "Região AWS onde os recursos são provisionados."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefixo usado no nome de todos os recursos (bucket, funções, repositórios ECR)."
  type        = string
  default     = "instagram-governadores"
}

variable "bucket_name" {
  description = "Nome do bucket S3 do data lake (Bronze/Silver/Gold). Precisa ser globalmente único."
  type        = string
}

variable "apify_api_token" {
  description = "Token da API Apify, usado só pela Lambda de extract. Nunca commitar em terraform.tfvars -- passar via TF_VAR_apify_api_token."
  type        = string
  sensitive   = true
}

variable "image_tag" {
  description = "Tag das imagens de container publicadas no ECR (SHA de commit -- sem default 'latest', ver ADR 0009)."
  type        = string
}

variable "create_github_oidc_provider" {
  description = "Se true, cria o aws_iam_openid_connect_provider do GitHub Actions. Uma conta AWS só pode ter um por URL -- se já existir (de outra infra), definir como false para reaproveitar via data source."
  type        = bool
  default     = true
}
