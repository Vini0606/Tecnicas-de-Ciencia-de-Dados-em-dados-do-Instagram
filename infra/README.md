# Infraestrutura AWS (Terraform)

Provisiona o que a reconstrução na nuvem precisa: bucket S3 (data lake), um repositório ECR e a
Lambda `rebuild`, como imagem de container. A `rebuild` baixa uma **tag de Coleta** do dataset
privado no Hugging Face e reconstrói Bronze, Silver e Gold no S3 (etapas determinísticas, ver
[ADR 0039](../docs/adr/0039-coleta-versionada-no-hf-bronze-fiel-e-aws-so-reconstroi.md)).
**Não há agendamento (EventBridge) nem extração (Apify) na nuvem**; extração e modelagem pesada
são locais. Ver também [ADR 0007](../docs/adr/0007-generalizar-deltarepository-para-s3-e-aposentar-is-cloud.md)
e [ADR 0009](../docs/adr/0009-publicar-imagens-das-lambdas-via-github-actions-com-oidc.md)
(publicação das imagens via GitHub Actions).

**Aviso de custo:** Lambda, S3 e ECR têm free tier, mas não são gratuitos indefinidamente —
revise os preços atuais antes de aplicar isto numa conta com cobrança ativa. Nada aqui é aplicado
automaticamente; você decide quando rodar `terraform apply` (que **nunca foi aplicado**).

## Pré-requisitos

- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.6
- [Docker](https://docs.docker.com/get-docker/) (para buildar a imagem da Lambda)
- AWS CLI configurado com credenciais válidas
- `jq` (usado por `scripts/build_and_push_lambdas.sh` para ler os outputs do Terraform)

## Passo a passo

1. **Definir as variáveis obrigatórias.** Copie `infra/terraform.tfvars.example` para
   `infra/terraform.tfvars` (já está no `.gitignore` — nunca commitar, tem o token do HF) e
   preencha, ou exporte como variáveis de ambiente:

   ```bash
   export TF_VAR_bucket_name="seu-bucket-unico-aqui"
   export TF_VAR_hf_token="seu-token-hf"             # sensível
   export TF_VAR_hf_dataset_repo="usuario/dataset"   # sensível
   export TF_VAR_image_tag="latest"  # sem default -- ver ADR 0009
   ```

2. **Provisionar o repositório ECR e a Role/Provider OIDC do GitHub Actions** (a Lambda só pode
   ser criada depois que a imagem existir no ECR):

   ```bash
   cd infra
   terraform init
   terraform apply \
     -target=aws_ecr_repository.lambdas \
     -target=aws_iam_openid_connect_provider.github \
     -target=aws_iam_role.github_actions_oidc
   ```

   Se falhar com `EntityAlreadyExists` no `aws_iam_openid_connect_provider.github` (a conta já
   tem um provedor OIDC do GitHub Actions), rode de novo com `-var="create_github_oidc_provider=false"`.

3. **Buildar e publicar a imagem** `rebuild`:

   ```bash
   cd ..
   ./scripts/build_and_push_lambdas.sh $(git rev-parse HEAD)
   ```

   Depois de configurar o GitHub Actions (seção "CD"), isso roda sozinho a cada merge relevante em
   `main`; o script fica como fallback manual.

4. **Provisionar o resto** (bucket S3, IAM, Lambda `rebuild`):

   ```bash
   cd infra
   terraform apply
   ```

## CD: publicação automática da imagem (GitHub Actions)

1. Pegue a ARN da role criada: `terraform output -raw github_actions_role_arn`
2. No GitHub, crie a repository variable `AWS_OIDC_ROLE_ARN` com esse valor
   (`gh variable set AWS_OIDC_ROLE_ARN --body "<arn>"`). A trust policy da role restringe quem pode
   assumi-la a `main` deste repositório.
3. Opcional: se `aws_region`/`project_name` não forem os defaults (`us-east-1` /
   `instagram-governadores`), defina também as variables `AWS_REGION` e `PROJECT_NAME`.

Todo push em `main` que passar no CI e mexer em `lambdas/**` ou `src/**` publica a imagem no ECR,
tagueada com o SHA do commit (`.github/workflows/build-lambdas.yml`). Isso **não** atualiza a
Lambda em execução — promover continua manual:

```bash
TF_VAR_image_tag=$(git rev-parse origin/main) terraform apply
```

## Reconstruir a partir de uma tag do HF

```bash
aws lambda invoke \
  --function-name "$(terraform output -raw rebuild_function_name)" \
  --payload '{"tag": "coleta_2026-10-06_piloto"}' \
  --cli-binary-format raw-in-base64-out \
  response.json
cat response.json
```

A Lambda tem 3008 MB, 5 GB de armazenamento efêmero (`/tmp`, onde o Snapshot é baixado) e timeout
de 900 s (teto da AWS). Seu papel IAM só lê/escreve no bucket do data lake; o acesso ao HF vem de
`HF_TOKEN`/`HF_DATASET_REPO` (variáveis sensíveis do Terraform).

## Destruir tudo

```bash
cd infra
terraform destroy
```

## Limitações conhecidas

- Sem retry/DLQ: uma falha na invocação manual não deixa rastro além do `response.json` e dos
  logs do CloudWatch.
- O Snapshot inteiro precisa caber no armazenamento efêmero e a reconstrução nos 15 minutos do Lambda.
- A trust policy da role OIDC do GitHub Actions está restrita a `ref:refs/heads/main` — publicar a
  partir de outro branch exige revisar `infra/main.tf`.
