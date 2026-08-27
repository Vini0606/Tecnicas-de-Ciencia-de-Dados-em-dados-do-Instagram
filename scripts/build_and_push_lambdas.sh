#!/usr/bin/env bash
# Builda e publica as 4 imagens das Lambdas (extract, transform, load,
# orchestrator) nos repositórios ECR criados pelo Terraform em infra/.
#
# Pré-requisito: já ter rodado, em infra/, pelo menos
#   terraform apply -target=aws_ecr_repository.lambdas
# (ver infra/README.md).
#
# Uso: ./scripts/build_and_push_lambdas.sh [tag]
#   tag  -- tag da imagem a publicar (default: latest, deve bater com a
#           variável image_tag do Terraform se for diferente do padrão).
set -euo pipefail

cd "$(dirname "$0")/.."  # raiz do repositório

TAG="${1:-latest}"
LAMBDAS=(extract transform load orchestrator)

REPO_URLS_JSON="$(cd infra && terraform output -json ecr_repository_urls)"

FIRST_REPO_URL="$(echo "$REPO_URLS_JSON" | jq -r 'to_entries[0].value')"
REGISTRY="${FIRST_REPO_URL%%/*}"
AWS_REGION="${AWS_REGION:-$(echo "$REGISTRY" | sed -E 's/^[0-9]+\.dkr\.ecr\.([a-z0-9-]+)\.amazonaws\.com$/\1/')}"

echo "Autenticando no ECR ($REGISTRY, região $AWS_REGION)..."
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$REGISTRY"

for name in "${LAMBDAS[@]}"; do
  repo_url="$(echo "$REPO_URLS_JSON" | jq -r --arg name "$name" '.[$name]')"
  image="${repo_url}:${TAG}"

  echo "Buildando $name -> $image"
  docker build -f "lambdas/$name/Dockerfile" -t "$image" .

  echo "Publicando $image"
  docker push "$image"
done

echo "Concluído. Rode 'terraform apply' em infra/ para atualizar as Lambdas com as novas imagens."
