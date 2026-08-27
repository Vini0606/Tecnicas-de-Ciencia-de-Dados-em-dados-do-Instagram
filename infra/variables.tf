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
  description = "Tag das imagens de container publicadas no ECR (ex.: latest, ou um SHA de commit)."
  type        = string
  default     = "latest"
}
