---
status: accepted
---

# Preparar o Streamlit para monitoramento diário: histórico em Gold primeiro, auto-refresh no dashboard, agendamento alternável — antes de subir para a AWS

## Contexto

O handoff de 2026-08-31 registrou o pedido do usuário: transformar o dashboard Streamlit num
monitoramento diário das métricas dos governadores, acompanhável em "tempo real", **antes** de
aplicar a infraestrutura AWS (`terraform apply` continua pendente). O handoff explicitamente pediu
para não redesenhar do zero — a ADR 0011 já é o design que antecipa esse cenário (landing zone,
extração consolidada, histórico em Gold) — e apontou quatro perguntas em aberto que só o usuário
podia responder.

Investigando o estado real do código antes de perguntar, duas das três decisões da ADR 0011 já
estavam implementadas, ao contrário do que o handoff presumia:

1. **Landing zone** (decisão 1) — implementada no PR #32 (`src/data_extract/ingestion.py::archive_raw_json`),
   com o layout por `run_id` já corrigido pela ADR 0014.
2. **Extração consolidada** (decisão 2) — implementada em `src/data_extract/ingestion.py::extract_and_land`,
   já usada pelos três pontos de entrada (`pipeline.py`, `scripts/run_apify_backfill.py`,
   `lambdas/extract/handler.py`).
3. **Histórico em Gold** (decisão 3) — **não implementada**. Nenhuma tabela `_history` existe;
   `EngagementAggregator.write` sempre grava em `mode="overwrite"` (via `write_delta`, que já aceita
   um parâmetro `mode` desde a ADR 0011, sem uso ainda). Único item real desta ADR ainda pendente.

Uma rodada de perguntas diretas ao usuário (via `AskUserQuestion`, seguindo o padrão de "pergunta a
pergunta, com recomendação" que o handoff sugeriu) resolveu os quatro pontos em aberto.

## Decisão

1. **"Tempo real" = auto-refresh periódico**, não streaming nem só um botão manual. O dashboard, já
   aberto, recarrega sozinho a cada N minutos, relendo a Gold via `DeltaRepository` — reflete a
   última execução do pipeline sem precisar reiniciar o app.
2. **Gold ganha histórico, mas só para engajamento por enquanto.** Nova tabela paralela
   `governor_engagement_history`, mesmo schema de `governor_engagement`
   (`GOLD_ENGAGEMENT_SCHEMA`, que já carimba `_run_id`/`_generated_at` em cada linha), escrita em
   `mode="append"` a cada execução — ao lado da tabela atual, que continua em `overwrite` sem
   nenhuma mudança para os consumidores existentes. `governor_sentiment`/`governor_clusters`/
   `governor_profile_clusters_engagement` **não** ganham histórico nesta ADR — ligados à modelagem
   (cadência própria, mais pesada, não roda a cada extração diária), diferente do engajamento, que é
   subproduto direto de cada extração. Estender histórico a eles fica deferido, mesmo raciocínio de
   "sem caso concreto ainda" que a ADR 0011 já usou para adiar outras peças.
3. **Agendamento com gate de custo alternável, não fixo.** EventBridge/cron passa a disparar o
   regime incremental/diário (`RESULTS_LIMIT` fixo, sem `--days`) na Lambda orquestradora. A
   confirmação de custo vira uma variável de configuração (env var/Terraform var na orquestradora,
   ex. `AUTO_CONFIRM_DAILY_EXTRACTION`) em vez de um comportamento fixo no código: `false` (padrão)
   bloqueia o disparo agendado sem confirmação humana e loga a estimativa de custo, igual ao gate
   manual de hoje (`pipeline.py`, issue #35); `true` deixa o disparo agendado prosseguir sozinho. O
   backfill nunca lê esse toggle — continua sempre manual, sem exceção, exatamente como a ADR 0011
   já havia decidido.
4. **Fonte de leitura do dashboard: continua local.** Nenhuma mudança em `DeltaRepository` ou nos
   caminhos que o dashboard lê. Migrar para S3 vira troca de configuração de path quando
   `terraform apply` de fato acontecer — `DeltaRepository` já abstrai isso via `storage_options`.
5. **Ordem de implementação: histórico em Gold primeiro, dashboard depois.** Sem histórico, não há
   tendência real para o dashboard mostrar — só o estado da última execução. Implementar o
   auto-refresh antes do histórico arriscaria redesenhar o dashboard duas vezes.

## Por que

Cada decisão veio de uma resposta explícita do usuário a uma pergunta com recomendação, não de uma
suposição:

- Auto-refresh: "Não pensei nisso, mas acho que um auto-refresh pode ser suficiente" — confirma a
  recomendação original (streaming seria complexidade desproporcional ao volume de dados; um botão
  manual não é "passivo" o suficiente para contar como monitoramento).
- Agendamento alternável: "Eu gostaria de uma mistura de 1 e 2. Poder alternar entre essas opções,
  como se eu pudesse 'habilitar' a confirmação automática" — rejeita explicitamente as duas opções
  fixas (sempre manual / sempre automático) em favor de um toggle.
- Fonte local: "Continua lendo local até a infra subir" — confirma a recomendação original,
  evitando trabalho adiantado sem bucket real para testar contra.
- Histórico primeiro: "Implementar histórico primeiro (landing zone + consolidação + tabelas
  append)" — a investigação de código mostrou que landing zone e consolidação já estavam prontas;
  o que resta desse pedido é só as tabelas de histórico.

## Opções consideradas

- **Streaming de verdade (websocket/push)** — rejeitada pelo usuário implicitamente ao aceitar a
  recomendação de auto-refresh; volume de dados (extração diária, não por segundo) não justifica a
  complexidade.
- **Agendamento 100% manual, sem EventBridge** ou **100% automático, sem confirmação** — ambas
  rejeitadas explicitamente; o usuário quer poder alternar entre os dois regimes, não fixar um.
- **Já desenhar o dashboard para ler S3 diretamente** — rejeitada; sem bucket real aplicado, seria
  implementação adiantada e não testável de verdade.
- **Dashboard primeiro, histórico depois** — rejeitada; o usuário priorizou explicitamente o
  histórico, evitando redesenhar o dashboard duas vezes.
- **Estender histórico a `governor_sentiment`/`governor_clusters` já nesta ADR** — não perguntada
  diretamente ao usuário; adiada por ora pelo mesmo raciocínio de "sem caso concreto ainda" que o
  projeto já usa em decisões análogas (ver ADR 0011, ADR 0004/0005). Fica como decisão futura
  separada se o monitoramento diário precisar de tendência de sentimento também.

## Consequências

- **Implementado nesta sessão:** `governor_engagement_history` (tabela Gold nova, append,
  `GOLD_ENGAGEMENT_SCHEMA` reutilizado sem mudança), `EngagementAggregator.write` ganha parâmetro
  `mode`, `pipeline.py` e `lambdas/load/handler.py` passam a escrever também na tabela de histórico,
  `settings.GOLD_ENGAGEMENT_HISTORY` novo, `DeltaRepository.load_engagement_history()` novo.
- **Não implementado nesta sessão, registrado como próximo passo:** auto-refresh no dashboard
  (`app.py`/`pages/01_exploratory.py`) consumindo `governor_engagement_history`; o toggle
  `AUTO_CONFIRM_DAILY_EXTRACTION` na Lambda orquestradora e a regra EventBridge correspondente em
  `infra/main.tf` (aditiva, como o README já apontava). Nenhum dos dois exige `terraform apply` para
  ser escrito — só para ser aplicado de fato, que continua sendo decisão manual do autor.
- Até o auto-refresh existir, o dashboard continua estático (lê a Gold uma vez, sem recarregar
  sozinho) — a tabela de histórico já existe e acumula dados, mas nada ainda a lê de volta.
- Sentimento e clusters continuam sem histórico — visualizar tendência dessas métricas ao longo do
  tempo fica fora de escopo até haver necessidade concreta, mesmo depois desta ADR.
