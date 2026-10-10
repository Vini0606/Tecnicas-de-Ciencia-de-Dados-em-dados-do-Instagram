output "bucket_name" {
  description = "Nome do bucket S3 do data lake."
  value       = aws_s3_bucket.data_lake.bucket
}

output "ecr_repository_urls" {
  description = "URL de cada repositório ECR, na ordem esperada pelo script de build/push."
  value       = { for name, repo in aws_ecr_repository.lambdas : name => repo.repository_url }
}

output "rebuild_function_name" {
  description = "Nome da Lambda de reconstrução -- aws lambda invoke --function-name <isto> --payload '{\"tag\": \"coleta_...\"}'."
  value       = aws_lambda_function.rebuild.function_name
}

output "github_actions_role_arn" {
  description = "ARN da role OIDC assumida pelo GitHub Actions para publicar imagens no ECR. Configure como repository variable AWS_OIDC_ROLE_ARN no GitHub (Settings > Secrets and variables > Actions > Variables)."
  value       = aws_iam_role.github_actions_oidc.arn
}
