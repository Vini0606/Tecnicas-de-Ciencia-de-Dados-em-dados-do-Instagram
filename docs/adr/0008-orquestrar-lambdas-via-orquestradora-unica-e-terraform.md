---
status: accepted
---

# Orquestrar as 3 Lambdas via uma Lambda orquestradora única, empacotada em containers e provisionada via Terraform

## Contexto

As 3 Lambdas (`lambdas/extract`, `lambdas/transform`, `lambdas/load`) já reproduzem o pipeline
Medallion no S3, mas nada as encadeava, e não existia nenhum IaC no repositório. A ADR 0007 já
tinha antecipado essa lacuna como o próximo passo natural, e o `README.md` cogitava "EventBridge
ou Step Functions" como opção em aberto, nunca decidida.

Três decisões precisavam ser tomadas: **como encadear** as Lambdas, **como empacotá-las**
(`pyarrow`/`deltalake` têm binários nativos pesados, que costumam quebrar em Lambda Layers
construídas fora do Amazon Linux), e **qual ferramenta de IaC** usar. Foram discutidas
diretamente com o autor do projeto.

## Decisão

1. **Orquestração: uma 4ª Lambda (`lambdas/orchestrator`)** invoca `extract` → `transform` →
   `load` em sequência via `boto3` (`lambda:InvokeFunction`, `InvocationType="RequestResponse"`),
   extrai o `run_id` da resposta de `extract` e repassa para `transform`/`load`. Se qualquer etapa
   retornar `statusCode != 200`, a cadeia é interrompida e o erro da etapa é propagado.
2. **Empacotamento: imagens de container** (`package_type = "Image"`), publicadas no ECR — não
   zip + Lambda Layer.
3. **IaC: Terraform**, em `infra/`.
4. Nenhum gatilho agendado (EventBridge/cron) foi configurado — o pipeline roda só quando
   invocado manualmente (`aws lambda invoke` na Lambda orquestradora).

## Por que

**Step Functions foi a alternativa recomendada e rejeitada.** Resolveria de forma nativa o
problema de passar o `run_id` entre etapas, teria retry automático por estado, e renderia um
diagrama de execução apresentável. Foi preterida em favor da solução mais simples e barata: uma
Lambda orquestradora comum, sem serviço de orquestração adicional para aprender/provisionar/pagar
— aceitando conscientemente a limitação de não ter retry nativo por etapa, e de a soma das 3
etapas precisar caber no teto de 15 minutos de timeout de Lambda (o hard limit da AWS).

**Container image em vez de zip + layer**: empacotar `pyarrow`/`deltalake` corretos para o
runtime do Lambda (Amazon Linux) via zip normalmente exige buildar dentro de um container de
qualquer forma (ex.: `sam build --use-container`) — a imagem de container evita essa etapa
intermediária e é o caminho mais robusto documentado pela própria AWS para dependências nativas
pesadas.

**Terraform em vez de AWS SAM/CDK**: é a ferramenta de IaC mais amplamente reconhecida fora do
ecossistema AWS (multi-cloud, um único binário, sem exigir Node.js como o CDK), o que tem valor
tanto para o TCC quanto para o currículo do autor.

## Opções consideradas

- **Step Functions** — rejeitada (ver acima): mais robusta, mas mais cara e complexa para o
  escopo atual do projeto.
- **EventBridge (regras encadeadas)** — rejeitada: sem estado nativo, passar o `run_id` entre
  etapas exigiria uma Lambda extra ou armazenamento intermediário (ex.: DynamoDB) só para isso —
  não é mais simples que a Lambda orquestradora escolhida, só mais desacoplada.
- **Zip + Lambda Layer** — rejeitada: inviável na prática para `pyarrow`/`deltalake` sem recorrer
  a um build em container de qualquer forma.
- **AWS SAM / AWS CDK** — rejeitadas: SAM é uma ferramenta mais estreita (só serverless AWS); CDK
  exigiria Node.js só para a CLI, além do Python já usado no projeto.
- **Gatilho agendado (EventBridge cron) desde já** — rejeitado por ora: sem uma cadência real
  definida, seria um recurso especulativo. Adicionar depois é uma mudança pequena e aditiva no
  mesmo `main.tf`.

## Consequências

- `lambdas/orchestrator/` é uma nova Lambda, com seu próprio `Dockerfile`/`requirements.txt`
  (só `boto3` — não precisa de `pandas`/`deltalake`, já que só invoca as outras 3).
- `lambdas/extract`, `lambdas/transform`, `lambdas/load` ganham `Dockerfile` (contexto de build =
  raiz do repositório, para poder copiar `src/`), sem nenhuma mudança de comportamento no
  `handler.py` de cada uma.
- Todo o provisionamento vive em `infra/` (Terraform) — ver `infra/README.md` para o passo a
  passo de deploy. Nenhum recurso foi criado numa conta AWS real como parte desta decisão; o
  código fica pronto para o autor aplicar quando quiser, com controle total de custo e
  credenciais.
- Limitação assumida e documentada: se o tempo somado de `extract` + `transform` + `load` um dia
  ultrapassar 15 minutos (ex.: `RESULTS_LIMIT` muito alto), a Lambda orquestradora estoura o
  timeout e a execução falha sem persistir progresso parcial. Se isso se tornar um problema real,
  a migração para Step Functions é o caminho natural — a lógica de cada etapa não muda, só quem
  as invoca.
