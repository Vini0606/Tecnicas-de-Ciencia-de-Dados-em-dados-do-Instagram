---
status: accepted
---

# Publicar as imagens das Lambdas via GitHub Actions, autenticando por OIDC, mantendo `terraform apply` manual

## Contexto

A ADR 0008 deixou o publicar as 4 imagens das Lambdas (`extract`, `transform`, `load`,
`orchestrator`) como um passo inteiramente manual: `scripts/build_and_push_lambdas.sh`, rodado
localmente, sempre que alguém decide atualizar as Lambdas. Nenhum gatilho automático foi
configurado por decisão explícita daquela ADR ("sem uma cadência real definida, seria um recurso
especulativo").

O CI existente (`.github/workflows/python-app.yml`) já roda testes e `ruff check` a cada push/PR
em `main`, mas não builda nem publica nada — é verificação de código, não produz artefato. Faltava
decidir se, e como, estender isso para automatizar a publicação das imagens, sem abrir mão do
controle consciente sobre quando a infraestrutura AWS real muda (motivo pelo qual `terraform
apply` nunca roda sozinho hoje, dado o custo de conta AWS ativa).

## Decisão

1. **Escopo**: um novo workflow do GitHub Actions builda e publica as 4 imagens no ECR
   automaticamente. `terraform apply` continua manual — publicar uma imagem nova no ECR não afeta
   nenhuma Lambda em execução até alguém promover explicitamente.
2. **Gatilho**: o novo workflow (`build-lambdas.yml`) dispara via `workflow_run`, condicionado ao
   workflow `CI` ter concluído com `success` em `main` — mais `workflow_dispatch` para disparo
   manual. Como `workflow_run` não suporta filtro nativo de `paths`, o primeiro step usa
   `dorny/paths-filter` comparando `github.event.workflow_run.head_sha` contra o commit pai, e só
   segue para o build se `lambdas/**` ou `src/**` mudaram.
3. **Build**: as 4 imagens são sempre buildadas juntas (sem detecção seletiva por Lambda), via
   `docker/build-push-action` com `cache-from`/`cache-to: type=gha` para reaproveitar as camadas
   de instalação de dependências entre execuções.
4. **Tag**: exclusivamente o SHA do commit. Nenhuma tag `latest` é publicada. `variables.tf` perde
   o default `"latest"` de `image_tag`, exigindo valor explícito em todo `terraform apply`.
5. **Autenticação**: OIDC — um `aws_iam_openid_connect_provider` + `aws_iam_role` novos em
   `infra/main.tf`, com trust policy restrita a
   `repo:Vini0606/Tecnicas-de-Ciencia-de-Dados-em-dados-do-Instagram:ref:refs/heads/main` (só
   `main`, nunca PRs/forks) e policy limitada às ações ECR necessárias
   (`GetAuthorizationToken`/`BatchCheckLayerAvailability`/`PutImage`/etc.) nos 4 repositórios. Sem
   credenciais estáticas (`AWS_ACCESS_KEY_ID`/`SECRET`) armazenadas como secret.
6. **Limpeza**: `aws_ecr_lifecycle_policy` em cada um dos 4 `aws_ecr_repository`, mantendo as
   últimas 10 imagens — necessário porque, sem tag `latest` sobrescrita, cada merge relevante em
   `main` passa a gerar 4 imagens novas e imutáveis.
7. **Bootstrap**: a Role/Provider OIDC entram na mesma fase 1 do `terraform apply` que já cria só
   os repositórios ECR (`terraform apply -target=aws_ecr_repository.lambdas
   -target=aws_iam_role.github_actions_oidc -target=aws_iam_openid_connect_provider.github`) — têm
   que existir antes da primeira execução da esteira.
8. **Promoção**: ao final do workflow, o SHA publicado e o comando de promoção são escritos em
   `$GITHUB_STEP_SUMMARY`. A convenção documentada é `TF_VAR_image_tag=$(git rev-parse
   origin/main) terraform apply`. `scripts/build_and_push_lambdas.sh` continua existindo como
   fallback manual local.

## Por que

**CD só até o ECR, não até a Lambda.** Automatizar `terraform apply` inteiro foi descartado desde
o início da discussão: o projeto já trata a conta AWS com cautela por causa de custo (ver
`infra/README.md`), e aplicar infraestrutura sozinho a cada merge tira exatamente o controle que
motivou manter isso manual na ADR 0008. Parar no ECR dá o maior ganho prático — elimina o passo
manual mais tedioso e propenso a erro, que é lembrar de buildar/publicar as 4 imagens certas — sem
abrir mão da decisão consciente de quando a Lambda real muda.

**Tag por SHA em vez de `latest`.** Lambda com `package_type = "Image"` fixa o digest no momento
do deploy: publicar uma imagem nova sob a mesma tag `latest` não faz o Terraform detectar mudança
nenhuma (a string `image_uri` não muda), então um `terraform apply` subsequente seria um no-op
silencioso. Tag por SHA torna a promoção uma mudança explícita e detectável na string do
`image_uri`, e casa com o padrão de rastreabilidade que o projeto já usa em outro lugar (`_run_id`,
`as_of_version` no Delta Lake).

**OIDC em vez de credenciais estáticas.** Elimina uma credencial de longa duração armazenada como
GitHub Secret, que precisaria rotação manual e representa um risco de vazamento maior que uma role
temporária federada. Mais trabalho inicial (mexe em `main.tf`), mas consistente com o cuidado que
o resto do projeto já tem com a conta AWS.

**Build das 4 imagens sempre juntas, sem detecção seletiva por Lambda.** O projeto tem um padrão
recorrente de não generalizar/otimizar preventivamente sem necessidade real (ADR 0004, ADR 0005).
Detecção seletiva por Lambda adicionaria lógica que é mais fonte de bug silencioso (esquecer de
rebuildar algo que devia) do que ganho real, já que o cache de camadas Docker via `type=gha` já
resolve a maior parte do custo de tempo de build repetido.

**Lifecycle policy no ECR desde já, e não adiada.** Diferente da detecção seletiva acima, aqui a
omissão tem custo real e crescente (armazenamento acumulando para sempre), não é especulação sobre
uma necessidade futura incerta — por isso entra junto nesta mesma decisão, e não como item futuro.

## Opções consideradas

- **CD completo até `terraform apply`** — rejeitada: tira o controle consciente sobre quando a
  infraestrutura AWS real muda, que é a premissa da ADR 0008.
- **Só CI mais robusto, sem publicar imagem nenhuma** — rejeitada: não resolve o problema real, que
  é o passo manual de build/push ser tedioso e propenso a erro.
- **Credenciais estáticas (access key/secret) em vez de OIDC** — rejeitada: mais simples de
  configurar, mas mantém uma credencial de longa duração como GitHub Secret, contrário à prática
  recomendada pela própria AWS e ao cuidado que o projeto já tem com a conta.
- **Tag `latest` mantida (sozinha ou junto com SHA)** — rejeitada: uma tag `latest` que nunca reflete
  o que está de fato deployado (já que a promoção é sempre manual) é uma fonte de confusão sem
  ganho real — o console do ECR já ordena por data de push.
- **Gatilho `push` direto com `paths`, sem gate no CI** — rejeitada: abriria a possibilidade de
  publicar uma imagem de um commit cujos testes falharam.
- **Detecção seletiva de build por Lambda** (`dorny/paths-filter` por diretório) — rejeitada por
  ora: complexidade que não se paga, dado que o cache de camadas Docker já reduz o custo de
  rebuildar as 4 imagens sempre.
- **Lifecycle policy adiada** — rejeitada: diferente da detecção seletiva, aqui a omissão tem custo
  monetário real e crescente, não é especulação.

## Consequências

- Novo workflow `.github/workflows/build-lambdas.yml`, separado do `python-app.yml` existente.
- `infra/main.tf` ganha `aws_iam_openid_connect_provider`, uma `aws_iam_role` para o GitHub
  Actions, e `aws_ecr_lifecycle_policy` para os 4 repositórios ECR.
- `infra/variables.tf`: `image_tag` perde o default `"latest"`.
- `infra/README.md` é atualizado: o passo de bootstrap (fase 1) passa a incluir os `-target` da
  Role/Provider OIDC, e um novo passo documenta a convenção de promoção via
  `TF_VAR_image_tag=$(git rev-parse origin/main) terraform apply`.
- `scripts/build_and_push_lambdas.sh` deixa de ser o caminho principal de publicação, mas continua
  existindo como fallback manual local (ex.: para rodar fora do fluxo do GitHub Actions).
- Limitação assumida: se um dia for necessário publicar a partir de outro branch que não `main`
  (ex.: um ambiente de staging), a trust policy da Role OIDC precisa ser revista — hoje está restrita
  a `ref:refs/heads/main`.
