# Escore composto e CMGR de engajamento

**Status:** a documentar
**Atualizada em:** 2026-10-11

> Justificativa do status: método decidido (ADR 0030) e implementado conforme a decisão (conferência no fechamento da spec
> #182, issue #193), mas a evidência registrada é de **conformidade com a decisão**, não de validade do escore. Os pesos são
> iguais por escolha, não calibrados, e a dimensão Consistência (o CMGR de engajamento) está pendente em todos os perfis do dado
> de 2026-10-04. Não há pergunta aberta formal nem notebook de avaliação; o que a ADR deixa para reabrir é a relação com o CMGR
> de audiência quando houver histórico.

## Pergunta de negócio

Como cada governador se posiciona entre os pares, numa nota única de 0 a 100 que combine alcance, ativação, qualidade,
profundidade e consistência? Aparece como **Escore composto** (Scorecard) na sub-aba do Resumo. É **relativo ao grupo** de
perfis: mede posição entre pares, não desempenho absoluto (`CONTEXT.md`).

O **CMGR de engajamento** responde a uma pergunta mais específica: o engajamento médio por post está crescendo ou caindo ao
longo dos meses de publicação? É a base da dimensão Consistência. Não confundir com o **CMGR de audiência** (crescimento de
seguidores entre coletas), que é outra taxa e hoje está pendente (`CONTEXT.md`, verbete "CMGR"; ADR 0030).

## Dados e série

Estágio pós-modelagem próprio (`GovernorScorecardScorer`, `src/modeling/governor_scorecard.py`), que lê Silver e Gold prontas e
grava `governor_scorecard`, 1 linha por governador (overwrite). Chave de junção: `inputUrl` normalizado (minúsculas, sem barra
final).

| Dimensão | Definição | Base |
|---|---|---|
| Alcance | média de `videoPlayCount` dos reels do perfil; rótulo "reproduções (plays)", nunca "visualizações únicas" | só reels (posts de feed não têm plays) |
| Ativação | média de `likesCount` dos reels / `followersCount` | reels |
| Qualidade | comentários positivos / comentários totais (`fonte == "comentario"` em `governor_sentiment`) | ver [sentimento.md](sentimento.md) |
| Profundidade | média de `commentsCount` / média de `videoPlayCount`, sobre reels com plays informados | reels |
| Consistência | CMGR de engajamento por data de publicação | reels e posts de feed, deduplicados por `id` |

- Universo: os perfis de `governor_engagement`. No dado de 2026-10-04 são **26** governadores, porque a Silver filtra
  governadores removidos de `governadores.xlsx`; os 27 citados no contexto da ADR 0030 e nos títulos da spec ficaram para trás
  (ADR 0030, "Como ficou implementado").
- Silver de 2026-10-04: cerca de 226 posts de ago/set-2026, o que não permite 4 meses válidos com pelo menos 3 posts maduros em
  nenhum perfil (ADR 0030). A Coleta final (90 dias, #256) ainda não foi feita.
- CMGR de audiência (`src/modeling/growth_history.py`): lê `governor_engagement_history` e `governor_sentiment_history`. Em
  2026-10-04 o histórico de engajamento tinha só 2 execuções (2026-09-19 e 2026-09-26), 7 dias de intervalo, e
  `governor_growth_metrics.cmgr` era nulo nos 26 perfis (`cmgr_n_periodos=1`, `cmgr_motivo="historico_insuficiente"`) (ADR
  0030, Contexto).

## Método escolhido

Segue a lógica de indicadores compostos do OECD Handbook: indicador bruto, normalização, ponderação, agregação (ADR 0030,
Contexto; docstring do módulo).

1. **Normalização:** min-máx de 0 a 100 entre os perfis, por dimensão. Dimensão nula de um perfil não entra no min-máx
   daquela dimensão. Amplitude zero (todos iguais) normaliza para 50, nem 0 nem 100.
2. **Agregação:** soma ponderada com pesos iguais: 0,20 com 5 dimensões; com uma dimensão pendente, os pesos são renormalizados
   (0,25 com 4). Perfil com menos de 4 das 5 dimensões fica sem escore e sem ranking (`MIN_DIMENSOES_PARA_ESCORE = 4`).
   `n_dimensoes` registra quantas entraram.
3. **Consistência (CMGR de engajamento por data de publicação, ADR 0030):**
   - engajamento do post = curtidas + comentários; média por post agregada por mês de publicação;
   - taxa composta mensal = `exp(inclinação) - 1` da regressão log-linear (`np.polyfit` de grau 1) sobre as médias mensais;
     o número de seguidores é constante por perfil e some na razão entre meses, por isso não entra;
   - janela de até 12 meses completos recentes (`JANELA_MAX_MESES`); o mês corrente fica de fora;
   - um mês só conta com pelo menos 3 posts (`MIN_POSTS_POR_MES`) e média positiva; posts com menos de 7 dias de vida são
     excluídos (`MIN_DIAS_DE_VIDA`, viés de maturidade: posts novos ainda acumulam curtidas);
   - menos de 4 meses válidos (`MIN_MESES_VALIDOS`): a Consistência fica pendente para o perfil
     (`consistencia_confiavel=False` na decisão; no código, `consistencia_pendente`).
4. **Onde roda:** último estágio de `run_deterministic_modeling` (`pipeline.py --run-modeling` / `scripts/run_modeling.py`) e,
   isolado, `scripts/run_governor_scorecard.py`. A Lambda `model` não roda o estágio (ADR 0030); a ADR 0039 diz depois que a
   nuvem só reconstrói as etapas determinísticas e que a modelagem pesada é local.
5. **CMGR de audiência** (`compute_cmgr`): `(valor_final / valor_inicial) ** (1 / n_meses) - 1` sobre a série mensal do último
   `followersCount` de cada mês; só é `confiavel` com pelo menos 6 períodos (`MIN_PERIODS_CONFIAVEL = 6`, limiar "arbitrário e
   documentado", sem base real para calibrar). Sempre ilustrativo enquanto o histórico for curto (ADR 0020, Ficha 7). Fica
   fora do Escore.

## Alternativas avaliadas

Registradas na ADR 0030 e no código.

| Alternativa | Vantagem | Desvantagem | Resultado |
|---|---|---|---|
| Consistência como CMGR de `governor_engagement_history` (especificação inicial) | Mede crescimento de audiência | Só 2 execuções, 7 dias de intervalo; taxa mensal sobre uma semana não tem significado estatístico | Rejeitada; CMGR de engajamento por data de publicação |
| Inclinação log-linear sobre as médias mensais | Mais estável que comparar só o primeiro e o último mês | Exige 4 meses válidos | Adotada |
| Comparar só primeiro e último mês | Simples | Menos estável | Rejeitada (ADR 0030) |
| Coluna `cmgr_engajamento_publicacao` em `governor_growth_metrics` | — | Não adotada; valor gravado na coluna `consistencia` de `governor_scorecard` | Não adotada |
| Mostrar escore com 2 ou 3 dimensões | Mais perfis ranqueados | "Enganaria" (ADR 0030, implementação) | Rejeitada; mínimo de 4 dimensões |
| Pesos diferentes entre as dimensões | — | — | Não registrado; pesos iguais por escolha |
| CMGR de audiência como sexta dimensão ou substituto da quinta | Mede crescimento de audiência | Histórico insuficiente hoje | Em aberto: reabrir quando houver histórico confiável (ADR 0030, Consequências) |

## Validação

- **Conformidade com a decisão** (ADR 0030, "Como ficou implementado", fechamento da spec #182, issue #193): a implementação
  (`governor_scorecard.py`, issue #184) seguiu a decisão sem mudar nenhum parâmetro.
- **Resultado sobre o dado de 2026-10-04:** a Consistência está pendente em todos os perfis; o escore vigente é a média das 4
  dimensões restantes (peso 0,25 cada), sobre 26 governadores. O escore muda sozinho à medida que a Silver acumular meses de
  publicação, sem alterar código (ADR 0030).
- **Diagnóstico do CMGR de audiência** (`notebooks/diagnostico_medallion/gold_growth_metrics.ipynb`, execução salva): 27 perfis,
  `cmgr` e `retencao` 100% nulos, `cmgr_confiavel=False` e `retencao_confiavel=False` em todos, 100% das linhas
  `ilustrativo=True`. Isto é limitação de tempo de operação, não um bug (docstring de `growth_history.py`).
- Testes automatizados: `tests/test_governor_scorecard.py`, `tests/test_growth_history.py`.
- **Não há** validação do escore em si (por exemplo, sensibilidade a pesos alternativos, estabilidade do ranking entre Coletas
  ou comparação com outra métrica). Não registrado.

## Limitações

- O escore é **relativo**: depende de quais perfis estão no grupo; uma mudança de universo (como 27 para 26) muda as notas.
- Consistência mede a **tendência do desempenho dos posts por mês de publicação**, não o crescimento de audiência; nunca
  rotular como "crescimento de audiência" (ADR 0030). O selo de confiabilidade deixa isso explícito.
- Pesos iguais não são calibrados; Alcance e Profundidade só usam reels; posts de feed e reels se sobrepõem na Silver, e só o
  CMGR deduplica por `id`.
- Dimensão com amplitude zero vira 50; perfil sem 4 dimensões não tem escore.
- O CMGR de audiência é ilustrativo por construção enquanto o histórico for curto; o limiar de 6 períodos é arbitrário.
- A ADR 0039 (Decisão 7) retira as tabelas `*_history` sem chamador e o "vs. execução anterior" do dashboard, deixando a
  comparação temporal para dentro de uma Coleta. O efeito sobre `governor_growth_metrics` e o CMGR de audiência não está
  registrado nas fontes consultadas.
- A coleta não captura compartilhamentos nem salvamentos (ADR 0018).
- A **Tendência** (ADR 0040, em avaliação) é outro conceito, calculada sobre a série bruta por data de publicação; a ADR 0040
  mantém o Escore composto como está ([tendencia.md](tendencia.md)).

## Vínculos

- Código: [`src/modeling/governor_scorecard.py`](../../src/modeling/governor_scorecard.py), [`src/modeling/growth_history.py`](../../src/modeling/growth_history.py), [`src/modeling/orchestration.py`](../../src/modeling/orchestration.py), [`scripts/run_governor_scorecard.py`](../../scripts/run_governor_scorecard.py), [`scripts/run_growth_metrics.py`](../../scripts/run_growth_metrics.py)
- ADR: [0030](../adr/0030-escore-composto-scorecard-com-consistencia-por-cmgr-de-engajamento-por-data-de-publicacao.md), [0020](../adr/0020-alinhamento-tcc-funil-cobra-race-nsm-ice-cmgr-e-reformulacao-do-dashboard-de-growth.md) (Ficha 7, CMGR de audiência), [0025](../adr/0025-comparacao-por-data-de-publicacao-conteudo-e-media-historica-perfil.md), [0039](../adr/0039-coleta-versionada-no-hf-bronze-fiel-e-aws-so-reconstroi.md), [0040](../adr/0040-tendencia-propria-substitui-comparativo-vs-mediana-e-catalogo-de-modelagens.md)
- Notebooks: [`gold_growth_metrics.ipynb`](../../notebooks/diagnostico_medallion/gold_growth_metrics.ipynb) (CMGR de audiência; não há notebook de diagnóstico para `governor_scorecard`)
- TCC (capítulo/seção): a preencher (a ADR 0020 prevê o CMGR como "ilustrativo" no Cap. 6/7)
