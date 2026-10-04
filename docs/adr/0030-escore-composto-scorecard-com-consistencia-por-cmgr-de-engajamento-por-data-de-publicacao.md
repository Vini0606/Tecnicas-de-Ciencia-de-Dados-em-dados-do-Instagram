---
status: accepted
---

# Escore composto (Scorecard) com Consistência medida por CMGR de engajamento por data de publicação

## Contexto

O dashboard ganha um Scorecard: ranking dos 27 governadores por um escore composto de 0 a 100, soma
ponderada (pesos iguais, 0,20) de cinco dimensões normalizadas min-máx entre os 27 perfis (Alcance,
Ativação, Qualidade, Profundidade, Consistência), seguindo a lógica de indicadores compostos do OECD
Handbook. As quatro primeiras dimensões saem de colunas que já existem (`videoPlayCount`, `likesCount`,
`commentsCount`, `followersCount`, rótulos de `governor_sentiment`).

A quinta dimensão, Consistência, foi especificada como o CMGR de `governor_engagement_history`. Levantamento
contra o dado real (2026-10-04): essa tabela tem só 2 execuções (`_run_id` de 2026-09-19 e 2026-09-26), com 7
dias de intervalo, e `governor_growth_metrics.cmgr` já é nulo nos 26 perfis (`cmgr_n_periodos=1`,
`cmgr_motivo="historico_insuficiente"`). Um crescimento mensal composto sobre uma semana não tem significado
estatístico. A ADR [0025](0025-comparacao-por-data-de-publicacao-conteudo-e-media-historica-perfil.md) já havia
estabelecido que métricas de conteúdo devem usar data de publicação, não execução; métricas de perfil
(seguidores) não têm data de publicação e não podem ser reconstruídas para o passado.

## Decisão

A Consistência do Scorecard é o **CMGR de engajamento por data de publicação** (coluna nova
`cmgr_engajamento_publicacao`), distinto do **CMGR de audiência** (seguidores entre coletas, que continua em
`governor_growth_metrics` e fica fora do escore enquanto for pendente).

Método, com parâmetros fixos nesta decisão:

- Engajamento médio por post agregado por mês de publicação; taxa composta mensal = `exp(inclinação) - 1` da
  regressão log-linear sobre as médias mensais (mais estável do que comparar só primeiro e último mês). O
  número de seguidores é constante por perfil e some na razão entre meses, por isso não entra.
- Janela de até 12 meses recentes completos; o mês corrente fica de fora.
- Mês só conta com pelo menos 3 posts; posts com menos de 7 dias de vida são excluídos (viés de maturidade:
  posts novos ainda acumulam curtidas).
- Perfil com menos de 4 meses válidos recebe `consistencia_confiavel=False` e a dimensão fica pendente para
  ele.

O escore é calculado por um módulo pós-modelagem próprio (fora do `EngagementAggregator`), gravado em nova
tabela Gold `governor_scorecard` declarada em `src/schemas_delta.py`; o dashboard só lê.

## Consequências

- Preserva as 5 dimensões do protótipo com dado real hoje, sem esperar acumular coletas.
- Muda o significado da dimensão: mede tendência do desempenho dos posts por mês de publicação, não
  crescimento de audiência. O selo de confiabilidade deixa isso explícito; nunca rotular como "crescimento de
  audiência".
- Dois CMGR convivem (engajamento por publicação, audiência por coleta); nomes explícitos evitam confusão.
- Quando o CMGR de audiência acumular histórico confiável, ele pode virar uma sexta dimensão ou substituir a
  quinta — decisão a reabrir então.
- Reverter exigiria recalcular a tabela e reexplicar o ranking, por isso o registro.
