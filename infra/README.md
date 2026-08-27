# Infraestrutura AWS (Terraform)

Provisiona os recursos para rodar o pipeline Medallion na nuvem: bucket S3 (data lake),
repositórios ECR e as 4 funções Lambda (`extract`, `transform`, `load`, `orchestrator`) como
imagens de container. Ver [ADR 0008](../docs/adr/0008-orquestrar-lambdas-via-orquestradora-unica-e-terraform.md)
para o porquê dessas escolhas.

**Aviso de custo:** Lambda, S3 e ECR têm free tier, mas não são gratuitos indefinidamente —
revise os preços atuais antes de aplicar isto numa conta com cobrança ativa. Nada aqui é aplicado
automaticamente; você decide quando rodar `terraform apply`.

## Pré-requisitos

- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.6
- [Docker](https://docs.docker.com/get-docker/) (para buildar as imagens das Lambdas)
- AWS CLI configurado com credenciais válidas (`aws configure` ou variáveis `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`)
- `jq` (usado por `scripts/build_and_push_lambdas.sh` para ler os outputs do Terraform)

## Passo a passo

1. **Definir as variáveis obrigatórias.** Crie `infra/terraform.tfvars` (já está no `.gitignore` —
   nunca commitar, tem o token da Apify) ou exporte como variáveis de ambiente:

   ```bash
   export TF_VAR_bucket_name="seu-bucket-unico-aqui"
   export TF_VAR_apify_api_token="seu-token-apify"
   ```

2. **Provisionar os repositórios ECR e a infraestrutura base** (as Lambdas só conseguem ser
   criadas depois que as imagens existirem no ECR, mas os repositórios em si podem/precisam ser
   criados primeiro):

   ```bash
   cd infra
   terraform init
   terraform apply -target=aws_ecr_repository.lambdas
   ```

3. **Buildar e publicar as 4 imagens** usando os URLs de repositório do passo anterior:

   ```bash
   cd ..
   ./scripts/build_and_push_lambdas.sh
   ```

4. **Provisionar o resto** (bucket S3, IAM, as 4 funções Lambda):

   ```bash
   cd infra
   terraform apply
   ```

5. **Rodar o pipeline completo** invocando a Lambda orquestradora:

   ```bash
   aws lambda invoke \
     --function-name "$(terraform output -raw orchestrator_function_name)" \
     --payload '{"links": ["https://www.instagram.com/exemplo/"]}' \
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
