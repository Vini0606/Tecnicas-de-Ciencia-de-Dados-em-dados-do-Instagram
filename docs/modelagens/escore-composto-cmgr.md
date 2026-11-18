# Escore composto e CMGR de engajamento

**Status:** a documentar (escore); Consistência em produção com o estimador validado em simulação (ADR 0047)
**Atualizada em:** 2026-11-18

> Justificativa do status: método do escore decidido (ADR 0030) e implementado conforme a decisão (conferência no fechamento da
> spec #182, issue #193), mas a evidência registrada é de **conformidade com a decisão**, não de validade do escore. Os pesos são
> iguais por escolha, não calibrados. A dimensão Consistência mudou de método em 2026-11-18 (ADR 0047): deixou de ser o CMGR
> sobre médias mensais (pendente em todos os perfis, inclusive na Coleta do TCC de 70 dias) e passou a ser a taxa mensal
> estimada por regressão por publicação, o estimador de contagem validado em simulação na ficha [tendencia.md](tendencia.md).
> Não há notebook de avaliação do escore em si; o que a ADR 0030 deixa para reabrir é a relação com o CMGR de audiência quando
> houver histórico.

## Pergunta de negócio

Como cada governador se posiciona entre os pares, numa nota única de 0 a 100 que combine alcance, ativação, qualidade,
profundidade e consistência? Aparece como **Escore composto** (Scorecard) na sub-aba do Resumo. É **relativo ao grupo** de
perfis: mede posição entre pares, não desempenho absoluto (`CONTEXT.md`).

O **CMGR de engajamento** responde a uma pergunta mais específica: o engajamento por publicação deste governador está crescendo
ou caindo ao longo do tempo, e com que incerteza? É a base da dimensão Consistência e do estado da **Tendência do engajamento**
mostrado no Scorecard (ADR 0047). Não confundir com o **CMGR de audiência** (crescimento de seguidores entre coletas), que é
outra taxa e hoje está pendente (`CONTEXT.md`, verbete "CMGR"; ADR 0030).

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
| Consistência | taxa mensal de variação do engajamento por publicação, por regressão (ADR 0047) | reels e posts de feed, deduplicados por `id`, sem fixadas, com >= 7 dias de vida |

- Universo: os perfis de `governor_engagement`. No dado de 2026-10-04 são **26** governadores, porque a Silver filtra
  governadores removidos de `governadores.xlsx`; os 27 citados no contexto da ADR 0030 e nos títulos da spec ficaram para trás
  (ADR 0030, "Como ficou implementado").
- Silver de 2026-10-04 (piloto): cerca de 226 posts de ago/set-2026. Coleta do TCC (2026-11): 70 dias, de 16/08 a 25/10/2026,
  cerca de 8,5 mil publicações, mas no máximo 3 meses elegíveis; por isso a regra de 4 meses válidos do método antigo deixava a
  Consistência pendente nos 26 perfis e foi substituída (ADR 0047).
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
3. **Consistência (taxa mensal por regressão por publicação, ADR 0047; função pública
   `estimar_tendencia_engajamento`):**
   - unidade = publicação (reel de `reels_clean` ou post de `posts_clean`), deduplicada por `id` (a linha de reel é a
     preferida), sem publicações fixadas (`isPinned`, ADR 0041) e com pelo menos 7 dias de vida (`MIN_DIAS_DE_VIDA`, viés de
     maturidade: publicações novas ainda acumulam curtidas);
   - modelo: `log(curtidas + comentários)` (piso 1) regredido em `t` = dias desde a primeira publicação do perfil / 30, mais
     `formato` (reel = 1, post = 0) como controle só quando o perfil tem os dois formatos (OLS, `statsmodels`); o número de
     seguidores é constante por perfil, por isso não entra;
   - taxa mensal = `exp(β) - 1`; IC de 95% = `exp(limites) - 1`; gravados em `consistencia_taxa_mensal` (= `consistencia`),
     `consistencia_ic_inferior`, `consistencia_ic_superior`, com `consistencia_n_publicacoes` e `consistencia_n_dias`;
   - confiável só com pelo menos 15 publicações (`MIN_PUBLICACOES`) em 10 dias distintos (`MIN_DIAS_DISTINTOS`); abaixo
     disso a Consistência fica pendente (`consistencia_pendente`) e o escore renormaliza para 4 dimensões;
   - **Tendência do engajamento** (`tendencia_engajamento`): "Dados insuficientes" se não confiável; "Subindo" se o limite
     inferior do IC > 0 e taxa >= +5% (`MIN_EFEITO_MENSAL`); "Caindo" se o limite superior < 0 e taxa <= -5%; "Estável" caso
     contrário. Mostrada como selo na sub-aba Scorecard, ao lado do valor normalizado e da taxa com IC em texto.
   - **Método anterior (ADR 0030, superado):** média por mês de publicação, regressão log-linear sobre as médias mensais,
     janela de 12 meses completos, mês válido com >= 3 posts, mínimo de 4 meses válidos; coluna `consistencia_n_meses`
     (removida).
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
| Inclinação log-linear sobre as médias mensais | Mais estável que comparar só o primeiro e o último mês | Exige 4 meses válidos; pendente em todos os perfis na Coleta do TCC (70 dias) | Adotada na ADR 0030; **superada** pela ADR 0047 |
| Comparar só primeiro e último mês | Simples | Menos estável | Rejeitada (ADR 0030) |
| Baixar o mínimo para 3 ou 2 meses válidos | Destrava a dimensão sem mudar o método | 2 pontos definem sempre uma reta; 3 ainda não dão incerteza; agosto e outubro são meses parciais | Rejeitada (ADR 0047) |
| Manter 4 meses e deixar pendente | Honesto | Escore com 4 dimensões em toda a entrega, apesar de ~8,5 mil publicações com data | Rejeitada (ADR 0047) |
| Regressão por publicação com formato como controle ("OLS com controles") | IC de 95%, controla a mistura de formato, usa dezenas de pontos por perfil; calibrado em simulação (falso alarme 4,3%, cobertura 95,3%) | Poder baixo para efeitos pequenos; melhor reta, não a história | **Adotada** (ADR 0047) |
| Coluna `cmgr_engajamento_publicacao` em `governor_growth_metrics` | — | Não adotada; valor gravado na coluna `consistencia` de `governor_scorecard` | Não adotada |
| Mostrar escore com 2 ou 3 dimensões | Mais perfis ranqueados | "Enganaria" (ADR 0030, implementação) | Rejeitada; mínimo de 4 dimensões |
| Pesos diferentes entre as dimensões | — | — | Não registrado; pesos iguais por escolha |
| CMGR de audiência como sexta dimensão ou substituto da quinta | Mede crescimento de audiência | Histórico insuficiente hoje | Em aberto: reabrir quando houver histórico confiável (ADR 0030, Consequências) |

## Validação

- **Conformidade com a decisão** (ADR 0030, "Como ficou implementado", fechamento da spec #182, issue #193): a implementação
  (`governor_scorecard.py`, issue #184) seguiu a decisão sem mudar nenhum parâmetro.
- **Resultado sobre o dado de 2026-10-04 (método antigo):** a Consistência estava pendente em todos os perfis; o escore era a
  média das 4 dimensões restantes (peso 0,25 cada), sobre 26 governadores. Na Coleta do TCC (70 dias) a situação não mudava, o
  que motivou a ADR 0047.
- **Estimador da Consistência (ADR 0047):** validado por simulação com verdade conhecida na ficha [tendencia.md](tendencia.md)
  (falso alarme 4,3%, cobertura do IC 95,3%, direção errada 0,7%; poder ~18% para efeitos moderados). O *backtest* com dado real
  previsto na ADR 0040 continua pendente; os limiares (15 publicações, 10 dias distintos, efeito mínimo de 5% ao mês) são os
  pontos de partida da ficha, não valores calibrados.
- **Diagnóstico do CMGR de audiência** (`notebooks/diagnostico_medallion/gold_growth_metrics.ipynb`, execução salva): 27 perfis,
  `cmgr` e `retencao` 100% nulos, `cmgr_confiavel=False` e `retencao_confiavel=False` em todos, 100% das linhas
  `ilustrativo=True`. Isto é limitação de tempo de operação, não um bug (docstring de `growth_history.py`).
- Testes automatizados: `tests/test_governor_scorecard.py`, `tests/test_growth_history.py`.
- **Não há** validação do escore em si (por exemplo, sensibilidade a pesos alternativos, estabilidade do ranking entre Coletas
  ou comparação com outra métrica). Não registrado.

## Limitações

- O escore é **relativo**: depende de quais perfis estão no grupo; uma mudança de universo (como 27 para 26) muda as notas.
- Consistência mede a **tendência do engajamento por publicação do próprio governador ao longo do tempo**, não o crescimento de
  audiência; nunca rotular como "crescimento de audiência" (ADR 0030). O selo de confiabilidade deixa isso explícito.
- O estimador devolve a melhor reta, não a história: campanha ou sazonalidade dentro da janela podem gerar estado enganoso, e
  "Estável" significa "sem evidência suficiente de variação", não "nada mudou" (poder baixo; ficha de tendência). O Scorecard
  não exibe a série junto do selo.
- Pesos iguais não são calibrados; Alcance e Profundidade só usam reels; posts de feed e reels se sobrepõem na Silver, e só a
  Consistência deduplica por `id` e exclui fixadas.
- Dimensão com amplitude zero vira 50; perfil sem 4 dimensões não tem escore.
- O CMGR de audiência é ilustrativo por construção enquanto o histórico for curto; o limiar de 6 períodos é arbitrário.
- A ADR 0039 (Decisão 7) retira as tabelas `*_history` sem chamador e o "vs. execução anterior" do dashboard, deixando a
  comparação temporal para dentro de uma Coleta. O efeito sobre `governor_growth_metrics` e o CMGR de audiência não está
  registrado nas fontes consultadas.
- A coleta não captura compartilhamentos nem salvamentos (ADR 0018).
- A **Tendência** (ADR 0040) está em produção só no Scorecard e só para contagem (ADR 0047); em NSM, Funil e "Todos", e para
  proporções, continua em avaliação ([tendencia.md](tendencia.md)).

## Vínculos

- Código: [`src/modeling/governor_scorecard.py`](../../src/modeling/governor_scorecard.py) (`estimar_tendencia_engajamento`), [`src/modeling/growth_history.py`](../../src/modeling/growth_history.py), [`src/modeling/orchestration.py`](../../src/modeling/orchestration.py), [`scripts/run_governor_scorecard.py`](../../scripts/run_governor_scorecard.py), [`scripts/run_growth_metrics.py`](../../scripts/run_growth_metrics.py), [`dashboard/screens/resumo_scorecard.py`](../../dashboard/screens/resumo_scorecard.py)
- ADR: [0047](../adr/0047-consistencia-por-regressao-por-publicacao-e-tendencia-no-scorecard.md), [0030](../adr/0030-escore-composto-scorecard-com-consistencia-por-cmgr-de-engajamento-por-data-de-publicacao.md), [0020](../adr/0020-alinhamento-tcc-funil-cobra-race-nsm-ice-cmgr-e-reformulacao-do-dashboard-de-growth.md) (Ficha 7, CMGR de audiência), [0025](../adr/0025-comparacao-por-data-de-publicacao-conteudo-e-media-historica-perfil.md), [0039](../adr/0039-coleta-versionada-no-hf-bronze-fiel-e-aws-so-reconstroi.md), [0040](../adr/0040-tendencia-propria-substitui-comparativo-vs-mediana-e-catalogo-de-modelagens.md), [0041](../adr/0041-filtro-de-periodo-unico-e-exclusao-de-publicacoes-fixadas.md)
- Notebooks: [`gold_growth_metrics.ipynb`](../../notebooks/diagnostico_medallion/gold_growth_metrics.ipynb) (CMGR de audiência; não há notebook de diagnóstico para `governor_scorecard`)
- TCC (capítulo/seção): a preencher (a ADR 0020 prevê o CMGR como "ilustrativo" no Cap. 6/7)
