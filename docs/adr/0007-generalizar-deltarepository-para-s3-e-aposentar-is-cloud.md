---
status: accepted
---

# Generalizar DeltaRepository para suportar S3, aposentando S3DataRepository e IS_CLOUD

## Contexto

O projeto tem um plano real de construir infraestrutura de engenharia de dados + MLOps na AWS,
com uma futura aplicação completa de monitoramento e tomada de decisão. Já existem três Lambdas
implementadas (`lambdas/extract`, `lambdas/transform`, `lambdas/load`) que replicam o pipeline
Medallion (Bronze/Silver/Gold) escrevendo **tabelas Delta** direto no S3, via `BronzeWriter` e
`EngagementAggregator` com `storage_options` (`AWS_REGION`, `AWS_S3_ALLOW_UNSAFE_RENAME`) — o
mesmo mecanismo de autenticação que o `deltalake` usa para acessar S3.

Paralelamente, `S3DataRepository` (`src/repositories/s3_repository.py`) e `IS_CLOUD`
(`config/settings.py`) existiam como uma segunda tentativa de suporte a nuvem, sem nenhum ponto de
uso em `src/`. Analisando o código, dois problemas ficaram claros:

1. **Incompatibilidade de formato**: `S3DataRepository` lê **parquet solto**
   (`s3://bucket/processed/{nome}.parquet`), enquanto os Lambdas produzem **tabelas Delta** em
   `bronze/`, `silver/`, `gold/`. Mesmo que `S3DataRepository` fosse ligado a algo hoje, não
   conseguiria ler os dados reais que os Lambdas escrevem.
2. **`DeltaRepository` (`src/repositories/delta_repository.py`) já é o formato certo e já aceita
   `storage_options`** — só tinha um bug latente: o construtor força `Path(gold_dir)` e
   `Path(silver_dir)`, e `pathlib.Path` normaliza barras duplas, corrompendo qualquer URI
   `s3://bucket/...` (viraria `s3:/bucket/...`).

Ou seja, o pipeline cloud real (os Lambdas) já usa o formato Delta; a única peça que falta para o
dashboard poder um dia ler do S3 é generalizar o repositório que já existe, não manter um segundo
formato paralelo.

## Decisão

- **Aposentar `S3DataRepository` e `IS_CLOUD`.** "Nuvem" deixa de ser um tipo de repositório ou um
  modo de execução (`if IS_CLOUD: ...`) e passa a ser só uma URI (`s3://...` vs. caminho local) +
  credenciais (`storage_options`) passadas ao `DeltaRepository` já existente.
- **Generalizar `DeltaRepository`** para aceitar tanto caminho local quanto URI S3 sem corromper
  nenhum dos dois: os campos internos passam a ser guardados como `str`, e a junção de caminho usa
  um helper que trata qualquer string com `"://"` como URI (concatenação simples) e cai no
  `pathlib.Path` de sempre para caminho local.
- **Remover a configuração morta correspondente** em `config/settings.py` (`S3_BUCKET`,
  `IS_CLOUD`, `S3_BRONZE_PREFIX`, `S3_SILVER_PREFIX`, `S3_GOLD_PREFIX`) — eram cópias duplicadas e
  não usadas dos mesmos defaults que os handlers dos Lambdas já leem direto de `os.environ`. O
  contrato de env vars dos Lambdas continua documentado no `README.md`, independente de
  `settings.py`.
- **Não ligar, por ora, o dashboard ao S3.** O dashboard de apresentação continua local, lendo
  Delta do disco via `DeltaRepository`. O "toggle" real de apontar `get_repository()`
  (`src/dashboard/loaders.py`) para um `s3://...` fica para quando o item de orquestração das
  Lambdas + IaC (Step Functions/EventBridge, Terraform/SAM) estiver implementado — hoje não há
  pipeline cloud de ponta a ponta para testar isso contra.

## Por que

Manter duas classes (`DeltaRepository` e `S3DataRepository`) implementando a mesma interface
(`DataRepository`) só por causa de onde o arquivo mora é uma distinção acidental, não uma
distinção de domínio — a mesma lição que a ADR 0002 já aplicou ao tratar `S3DataRepository` como
"a mesma interface, outro backend" antes de se saber que o backend real (os Lambdas) usa Delta, não
parquet. Generalizar `DeltaRepository` elimina a duplicação e corrige, de graça, um bug que
impediria o próprio `S3DataRepository` de funcionar corretamente mesmo que fosse mantido.

## Opções consideradas

- **Consertar `S3DataRepository` para ler Delta em vez de parquet** — rejeitada: duplicaria toda a
  lógica que `DeltaRepository` já tem (versionamento via `as_of_version`/`as_of_timestamp`,
  histórico de tabela), sem nenhum motivo de domínio para dois repositórios Delta distintos.
- **Deletar tudo (`S3DataRepository`, `IS_CLOUD`) sem generalizar `DeltaRepository`** — rejeitada:
  descartaria a intenção real de MLOps na AWS; o bug do `pathlib` continuaria existindo,
  silenciosamente, para o dia em que alguém tentasse apontar `DeltaRepository` para o S3.
- **Já ligar o dashboard ao S3 agora** — rejeitada por ora: sem os Lambdas orquestrados
  (Step Functions/EventBridge) e sem IaC, não há um pipeline cloud real de ponta a ponta para
  validar a leitura contra dados verdadeiros — decisão fica para quando essa peça existir.

## Consequências

- `src/repositories/s3_repository.py` foi removido; `config/settings.py` não expõe mais
  `S3_BUCKET`, `IS_CLOUD`, `S3_BRONZE_PREFIX`, `S3_SILVER_PREFIX`, `S3_GOLD_PREFIX`.
- `DeltaRepository` pode, em teoria, ler de um `s3://...` hoje (dado `storage_options` com
  credenciais válidas) — mas nada em `src/dashboard/loaders.py` ainda o aponta para lá; isso é
  trabalho futuro, condicionado à orquestração das Lambdas.
- Quando a orquestração das Lambdas + IaC for implementada, a forma natural de o dashboard ler do
  S3 é instanciar `DeltaRepository(gold_dir="s3://bucket/gold", storage_options={...})` — nenhuma
  classe nova precisa ser criada para isso.
