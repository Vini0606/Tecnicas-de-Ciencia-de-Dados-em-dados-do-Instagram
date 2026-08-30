---
status: accepted
---

# Preparar a arquitetura Medallion para um monitor contínuo de redes sociais: landing zone de dado bruto, extração consolidada e histórico em Gold

## Contexto

O roadmap do projeto (registrado no `/handoff` de 2026-08-29 e numa sessão de `/grilling` em 2026-08-30) inclui transformar o projeto num monitor contínuo de redes sociais — ingestão diária incremental, mais atualizações periódicas que podem exigir re-raspar um período específico ou o histórico inteiro. Ao explorar se a arquitetura Medallion atual (Bronze append-only em Delta Lake via `BronzeWriter`, Silver deduplicada por `id` via `deduplicate_latest`, Gold agregada) já sustenta isso, três lacunas concretas apareceram no código, não hipotéticas:

1. **A Bronze descarta campos silenciosamente.** `conform_to_schema` (`src/delta_io.py`) documenta explicitamente: *"Colunas presentes no DataFrame e ausentes do schema são descartadas"*. `BRONZE_POSTS_SCHEMA`/`BRONZE_REELS_SCHEMA` (`src/schemas_delta.py`) declaram só ~14-17 campos fixos por registro. Evidência de que isso já causou confusão: `PostCleaner._drop_noise_columns` (Silver) tenta remover `hashtags`, `mentions`, `images`, `childPosts`, `taggedUsers`, `coauthorProducers`, `musicInfo` — nenhum desses campos está no schema da Bronze, então já foram descartados antes de chegar lá; esse trecho da Silver é código morto, sinal de que a suposição "a Bronze passa tudo adiante" não é verdade e ninguém percebeu.
2. **A sequência "raspar perfis+posts+reels e escrever na Bronze" está duplicada 3x**, sem nenhum compartilhamento: `pipeline.py` (branch de extração de `run_medallion_pipeline`), `scripts/run_apify_backfill.py` e `lambdas/extract/handler.py`. Isso já quase causou uma inconsistência nesta mesma sessão, ao criar o script de backfill.
3. **Gold é sempre sobrescrita (`mode="overwrite"`), nunca acumula histórico** — apesar de todo escritor de Gold (`EngagementAggregator.write`, `ModelEnricher.write_sentiment`/`write_clusters`/`write_profile_clusters_engagement`) já carimbar `_run_id`/`_generated_at` em cada linha. O Delta Lake tecnicamente preserva versões antigas via time travel (nenhum `VACUUM` é chamado em lugar nenhum do código, e `DeltaRepository` já expõe `as_of_version`/`get_table_history`), mas isso é acidental, não um design deliberado — frágil a uma futura limpeza de espaço.

## Decisão

- Introduzir uma **landing zone nova, anterior à Bronze**: JSON bruto por `run_id`, sem schema (não passa por `conform_to_schema`), imutável — arquivo de fidelidade total contra a perda silenciosa de campos descrita acima.
- **Consolidar** a sequência "raspar perfis+posts+reels e escrever na Bronze" — hoje triplicada em `pipeline.py`, `scripts/run_apify_backfill.py` e `lambdas/extract/handler.py` — num único ponto de código compartilhado. O arquivamento na landing zone entra nesse mesmo ponto, para que nenhum caminho de ingestão futuro (uma quarta rede social, um quarto ponto de entrada) possa esquecê-lo.
- Re-raspar um **período específico** e re-raspar **o histórico inteiro** continuam sendo a mesma operação (`scripts/run_apify_backfill.py`, variando só `--days`) — nenhum mecanismo novo é necessário para essa distinção.
- Dois regimes de segurança distintos e permanentes: **ingestão incremental/diária** (custo limitado por natureza — `RESULTS_LIMIT` fixo, sem janela de data) pode futuramente rodar sem confirmação manual; **backfill** (custo variável, escalando com `--days`) sempre exige confirmação manual (`--yes` + estimativa de custo) e nunca deve virar um job agendado sozinho.
- Gold ganha uma dimensão de tempo através de **tabelas novas e paralelas de histórico** (ex.: `governor_engagement_history`), escritas em modo `append`. As tabelas Gold atuais (`governor_engagement`, `governor_sentiment`, `governor_clusters`, `governor_profile_clusters_engagement`) continuam em `overwrite`, uma linha por governador, sem nenhuma mudança nos consumidores existentes (dashboard incluso) — falta só o destino em `append`, já que `_run_id`/`_generated_at` já existem em cada linha.
- Só a **Gold** ganha essa dimensão de tempo por enquanto. A Silver continua representando o estado atual deduplicado (`deduplicate_latest` por `id`) — rastrear a evolução de métricas por post/reel individual ao longo do tempo fica fora de escopo até haver uma necessidade concreta.
- **Nenhuma mudança de código acontece agora.** Este ADR documenta a direção arquitetural para quando a implementação de fato começar (ingestão diária automática, ciclo de atualização periódica).

## Por que

As três lacunas do Contexto já são reais hoje, não especulativas — diferente das frentes de multi-entidade/multi-rede-social (ver [ADR 0004](0004-manter-pipelines-separados-por-entidade-sem-generalizar-schema-agora.md) e [ADR 0005](0005-multi-rede-social-engajamento-comparavel-em-gold-sem-generalizar-bronze-silver.md)), que foram deliberadamente adiadas por não terem um caso concreto ainda. Aqui, a duplicação de extração já existe em três arquivos e quase causou uma inconsistência nesta sessão; a Bronze já descarta campos hoje, com uma prova disso (código morto na Silver); e Gold já carrega os campos de auditoria (`_run_id`/`_generated_at`) sem aproveitá-los. Corrigir essas lacunas agora não é generalizar para um caso hipotético — é fechar um buraco já aberto.

Optar por tabelas de histórico *paralelas* em vez de migrar as tabelas Gold existentes segue o mesmo princípio de menor risco que o projeto já usa: `governor_clusters` (por reel) e `governor_profile_clusters_engagement` (por governador) já são, no código, "deliberadamente separados" em vez de uma tabela genérica — o mesmo raciocínio se aplica aqui.

## Opções consideradas

- **Afrouxar o schema da Bronze para ser permissivo**, em vez de criar uma landing zone separada — rejeitada: mudança maior e mais arriscada; Delta/Parquet se beneficia de schema estável, e a Silver já assume colunas tipadas específicas vindas da Bronze.
- **Manter a duplicação da extração** e replicar manualmente a lógica de landing zone nos três pontos de entrada — rejeitada: já quase causou uma inconsistência nesta mesma sessão; consolidar agora é mais barato do que o risco de divergência futura.
- **Re-raspar o histórico inteiro todo mês** como rotina padrão de "atualidade" — rejeitada: o custo escala linearmente com o tamanho do histórico (ex.: ~$193 por execução para 2 anos, ~$2.300/ano se mensal), enquanto o motivo real de "atualidade" (engajamento ainda em mudança) se concentra em conteúdo recente. A Silver já atualiza métricas de posts antigos de graça caso um re-scrape aconteça; o backfill completo continua disponível como operação pontual, não como rotina obrigatória.
- **Confiar no time travel implícito do Delta Lake** (`as_of_version`/`get_table_history`, já exposto em `DeltaRepository`) para reconstruir tendência histórica, em vez de tabelas de histórico dedicadas — rejeitada: frágil, depende de detalhes internos do motor Delta (retenção padrão, ninguém nunca rodar `VACUUM`) nunca configurados deliberadamente para esse fim.
- **Migrar as tabelas Gold existentes direto para `append`**, com os consumidores atuais passando a filtrar "a linha mais recente" via `deduplicate_latest` — rejeitada por ora: exigiria mudar todo consumidor existente (dashboard incluso) sem necessidade concreta ainda; tabelas de histórico paralelas entregam o mesmo resultado sem esse risco.

## Consequências

- Nenhum código muda nesta sessão — os itens acima ficam como direção arquitetural registrada, não implementação. A implementação de cada peça (landing zone, consolidação da extração, tabelas de histórico em Gold) fica para quando o trabalho de fato começar.
- A propagação de `onlyPostsNewerThan`/`resultsLimit` para a lambda `extract`/`orchestrator` e a extensão do padrão de consolidação para os estágios de Silver/Gold continuam como decisões futuras separadas, registradas em memória de projeto (não neste ADR): decisão sobre propagação para lambda, e decisão sobre consolidar Silver/Gold também.
- Até a landing zone ser implementada, qualquer campo que a Apify retorne e não esteja nos schemas fixos de Bronze (`BRONZE_PROFILES_SCHEMA`, `BRONZE_POSTS_SCHEMA`, `BRONZE_REELS_SCHEMA`) continua sendo perdido permanentemente no momento da extração.
- Até as tabelas de histórico de Gold existirem, não há como visualizar tendência de engajamento ao longo do tempo no dashboard — só o estado mais recente.
