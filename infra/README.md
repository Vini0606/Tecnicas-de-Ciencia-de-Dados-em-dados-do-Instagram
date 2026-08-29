# Infraestrutura AWS (Terraform)

Provisiona os recursos para rodar o pipeline Medallion na nuvem: bucket S3 (data lake),
repositórios ECR e as 5 funções Lambda (`extract`, `transform`, `load`, `orchestrator`, `model`) como
imagens de container. Ver [ADR 0008](../docs/adr/0008-orquestrar-lambdas-via-orquestradora-unica-e-terraform.md)
para o porquê dessas escolhas, e [ADR 0009](../docs/adr/0009-publicar-imagens-das-lambdas-via-github-actions-com-oidc.md)
para a publicação automática das imagens via GitHub Actions.

`model` (clustering de perfil de governador por Engajamento, Fase 2) fica **fora** da cadeia da
orquestradora de propósito -- é invocada manualmente, como a modelagem local também é opt-in (ver
"Rodar o clustering de perfil" abaixo e ADR 0001).

**Aviso de custo:** Lambda, S3 e ECR têm free tier, mas não são gratuitos indefinidamente —
revise os preços atuais antes de aplicar isto numa conta com cobrança ativa. Nada aqui é aplicado
automaticamente; você decide quando rodar `terraform apply`.

## Pré-requisitos

- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.6
- [Docker](https://docs.docker.com/get-docker/) (para buildar as imagens das Lambdas)
- AWS CLI configurado com credenciais válidas (`aws configure` ou variáveis `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`)
- `jq` (usado por `scripts/build_and_push_lambdas.sh` para ler os outputs do Terraform)

## Passo a passo

1. **Definir as variáveis obrigatórias.** Copie `infra/terraform.tfvars.example` para
   `infra/terraform.tfvars` (já está no `.gitignore` — nunca commitar, tem o token da Apify) e
   preencha, ou exporte como variáveis de ambiente:

   ```bash
   export TF_VAR_bucket_name="seu-bucket-unico-aqui"
   export TF_VAR_apify_api_token="seu-token-apify"
   export TF_VAR_image_tag="latest"  # sem default -- ver ADR 0009
   ```

2. **Provisionar os repositórios ECR e a Role/Provider OIDC do GitHub Actions** (as Lambdas só
   conseguem ser criadas depois que as imagens existirem no ECR, mas os repositórios em si e a
   Role OIDC podem/precisam ser criados primeiro — a Role precisa existir antes da primeira
   publicação automática de imagem, ver seção "CD" abaixo):

   ```bash
   cd infra
   terraform init
   terraform apply \
     -target=aws_ecr_repository.lambdas \
     -target=aws_iam_openid_connect_provider.github \
     -target=aws_iam_role.github_actions_oidc
   ```

   Se isso falhar com `EntityAlreadyExists` no `aws_iam_openid_connect_provider.github` (a conta já
   tem um provedor OIDC do GitHub Actions criado por outra infraestrutura — só pode existir um por
   conta), rode de novo com `-var="create_github_oidc_provider=false"`.

3. **Buildar e publicar as 5 imagens** usando os URLs de repositório do passo anterior:

   ```bash
   cd ..
   ./scripts/build_and_push_lambdas.sh $(git rev-parse HEAD)
   ```

   A partir daqui, depois de configurar o GitHub Actions (seção "CD" abaixo), esse passo passa a
   rodar sozinho a cada merge relevante em `main` — este script continua existindo só como
   fallback manual.

4. **Provisionar o resto** (bucket S3, IAM, as 5 funções Lambda):

   ```bash
   cd infra
   terraform apply
   ```

## CD: publicação automática das imagens (GitHub Actions)

Depois da fase 1 do bootstrap acima, configure o GitHub Actions para autenticar via OIDC:

1. Pegue a ARN da role criada:

   ```bash
   terraform output -raw github_actions_role_arn
   ```

2. No GitHub, crie a repository variable `AWS_OIDC_ROLE_ARN` com esse valor (Settings > Secrets
   and variables > Actions > Variables > New repository variable, ou
   `gh variable set AWS_OIDC_ROLE_ARN --body "<arn>"`). Não é segredo — a trust policy da role já
   restringe quem pode assumi-la a `main` deste repositório.
3. Opcional: se `aws_region`/`project_name` não forem os defaults (`us-east-1` /
   `instagram-governadores`), defina também as repository variables `AWS_REGION` e `PROJECT_NAME`.

A partir daí, todo push em `main` que passar no CI e mexer em `lambdas/**` ou `src/**` publica as
5 imagens no ECR automaticamente, tagueadas com o SHA do commit (ver
`.github/workflows/build-lambdas.yml` e [ADR 0009](../docs/adr/0009-publicar-imagens-das-lambdas-via-github-actions-com-oidc.md)).
Isso **não** afeta as Lambdas em execução — promover continua sendo manual:

```bash
TF_VAR_image_tag=$(git rev-parse origin/main) terraform apply
```

(O SHA publicado e esse comando também aparecem no resumo de cada execução do workflow
`build-lambdas.yml`, em `$GITHUB_STEP_SUMMARY`.)

5. **Rodar o pipeline completo** invocando a Lambda orquestradora:

   ```bash
   aws lambda invoke \
     --function-name "$(terraform output -raw orchestrator_function_name)" \
     --payload '{"links": ["https://www.instagram.com/exemplo/"]}' \
     --cli-binary-format raw-in-base64-out \
     response.json
   cat response.json
   ```

6. **(Opcional, manual) Rodar o clustering de perfil por Engajamento** invocando `model`
   diretamente -- não faz parte da cadeia acima, precisa de um `run_id` (reaproveite o de uma
   execução anterior da orquestradora, ou gere um novo):

   ```bash
   aws lambda invoke \
     --function-name "$(terraform output -raw model_function_name)" \
     --payload '{"run_id": "20260829_120000_abcdef12"}' \
     --cli-binary-format raw-in-base64-out \
     response.json
   cat response.json
   ```

## Destruir tudo

```bash
cd infra
terraform destroy
```

## Limitações conhecidas

- A orquestração é uma única Lambda invocando as outras três em sequência via `boto3` — não há
  retry automático por etapa, e o tempo total (extract + transform + load) precisa caber no teto
  de 15 minutos de timeout de Lambda. Ver ADR 0008 para a alternativa rejeitada (Step Functions).
- Não há gatilho agendado (EventBridge/cron) configurado — o pipeline roda só quando invocado
  manualmente. Adicionar um agendamento é uma mudança pequena e aditiva neste mesmo `main.tf`.
- O workflow `build-lambdas.yml` builda as 5 imagens sempre juntas (sem detecção seletiva por
  Lambda) — decisão deliberada, ver ADR 0009.
- `model` não tem retry/DLQ configurado (mesmo padrão simples das outras Lambdas) -- uma falha na
  invocação manual não deixa rastro além do próprio `response.json`/logs do CloudWatch.
- A trust policy da role OIDC do GitHub Actions está restrita a `ref:refs/heads/main` — publicar a
  partir de outro branch (ex.: staging) exige revisar `infra/main.tf`.
