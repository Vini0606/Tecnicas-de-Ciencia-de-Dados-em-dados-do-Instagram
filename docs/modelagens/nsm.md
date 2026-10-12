# Engajamento qualificado (NSM)

**Status:** validada
**Atualizada em:** 2026-10-11

> Justificativa do status: a ADR 0020 e o `CONTEXT.md` registram a verificação com dado real (27 perfis, 2026-09-19): o ranking
> por NSM muda de posição para 25 dos 27 perfis frente ao ranking por engajamento bruto, e a métrica deixou de levar o selo "em
> validação". O critério validado é o de **diferenciar** o ranking do bruto; não há, nas fontes, validação de que o ranking
> por NSM acompanha algum critério externo (ver "Validação" e "Limitações"). A verificação é anterior à inclusão dos
> comentários de posts (ADR 0034), que altera os números.

## Pergunta de negócio

Qual governador gera engajamento de **qualidade** (reação positiva do público), e não só de volume? O engajamento bruto
(curtidas e comentários) não distingue um post com muitos comentários negativos de um com muitos positivos. O analista vê o
resultado na sub-aba NSM do Resumo, com o nome **Engajamento qualificado** (a sigla NSM não aparece na interface), como
índice de 0 a 100 (min-máx entre os perfis), contrastado com o ranking por engajamento bruto (`CONTEXT.md`).

## Dados e série

- Entradas: `governor_sentiment` (apenas linhas com `fonte == "comentario"`, coluna `sentiment_label`) e `governor_engagement`
  (colunas `TOTAL ENGAJAMENTO` e `count`), juntadas por `inputUrl` com `merge` externo (`NsmScorer.score`,
  `src/features/gold/nsm_scorer.py`). Um perfil presente em só uma das tabelas entra com 0 no lado ausente.
- `TOTAL ENGAJAMENTO` é a soma de `likesSum` e `commentsSum`, sem peso (`src/features/gold/engagement_aggregator.py`).
- Saída: tabela Gold `governor_nsm`, 1 linha por perfil (`inputUrl`), com `n_comentarios_positivos`,
  `n_comentarios_totais`, `proporcao_positivos`, `total_engajamento`, `count_posts`, `alcance_medio` e `nsm`.
- Granularidade temporal: uma foto por execução; não há tabela `_history` de NSM (`gold_nsm.ipynb`). A ADR 0033 estabelece que
  o histórico do NSM não é necessário para o comparativo.
- Tamanho: 27 perfis na verificação de 2026-09-19 (ADR 0020). O universo posterior é 26 governadores (ADR 0030, "Como ficou
  implementado"). Os comentários de posts de feed passaram a entrar a partir da ADR 0034; a Coleta final (90 dias, #256) ainda
  não foi feita.

## Método escolhido

`NSM = (comentários positivos / comentários totais) x alcance médio`, por perfil (ADR 0020, Ficha 5; fixada na ADR, "não
reaberta" no código).

- **Alcance médio é um proxy**: `TOTAL ENGAJAMENTO / count` (engajamento médio por publicação). O Instagram não expõe alcance
  para posts estáticos e `governor_engagement` não guarda alcance. A interface o chama de "alcance estimado por engajamento"
  (`CONTEXT.md`, verbete "Alcance"), e a ADR 0021 separa esse proxy do dado real de visualizações (`videoPlayCount`) usado no
  Funil.
- Perfil sem comentários: `proporcao_positivos = 0`; perfil sem posts: `alcance_medio = 0`; nenhum caso gera erro nem `NaN`.
- Estágio pós-modelagem (depende de `governor_sentiment` e `governor_engagement`), executado em
  `run_deterministic_modeling` (`src/modeling/orchestration.py`); fora do `EngagementAggregator`, porque o engajamento roda
  antes da modelagem de sentimento.
- Apresentação: índice 0 a 100 (min-máx entre os perfis). O comparativo contra a mediana dos demais é em **pontos do índice**,
  e não em percentual, porque um percentual sobre um índice min-máx exagera quando a mediana é baixa; em "Todos", compara a
  média do grupo com a mediana do grupo e indica assimetria, não desempenho (ADR 0033). Os dois rankings listam todos os
  governadores com NSM, com rolagem (ADR 0033).

## Alternativas avaliadas

Só constam as alternativas registradas nos ADRs.

| Alternativa | Vantagem | Desvantagem | Resultado |
|---|---|---|---|
| Calcular no `EngagementAggregator` original | Reuso | Inverteria a ordem do pipeline (engajamento roda antes do sentimento) e forçaria recomputação (ADR 0020, "Por que") | Rejeitada; estágio pós-modelagem |
| Engajamento bruto (curtidas + comentários) como medida de desempenho | Simples | Não separa reação positiva de negativa (ADR 0020; docstring de `nsm_scorer.py`) | Mantido apenas como contraste ("bruto vs. qualificado") |
| Comparativo em percentual sobre o índice (ADR 0033) | Familiar | Exagera quando a mediana é baixa | Rejeitada; pontos do índice |
| Comparar com a média em "Todos" (ADR 0033) | — | A média é puxada por poucos perfis altos; o líder fica em 100 e comprime os demais | Substituída por média contra mediana, em tom neutro |
| Projeção ou comparação com execuções anteriores (ADR 0033) | — | Não requisitada; o histórico do NSM não é necessário | Fora de escopo |
| Alcance real (visualizações) no lugar do proxy | Dado real | Só existe para vídeo; posts estáticos não têm `videoPlayCount` | Não adotada; proxy declarado |
| Outras fórmulas de qualificação (por exemplo, sentimento ponderado pelo score do classificador) | — | — | Não registrado |

## Validação

- **Verificação com dado real (ADR 0020, 2026-09-19)**, após o backfill que corrigiu o link do Espírito Santo e completou a
  modelagem determinística com 27 perfis: o critério de aceite da issue #90 (ranking por NSM diferir do ranking por engajamento
  bruto em pelo menos 1 caso) foi confirmado. **25 dos 27 perfis mudam de posição** entre os dois rankings.
  - O 1º lugar muda: `tarcisiogdf` ultrapassa `romeuzemaoficial`, que lidera em engajamento bruto mas tem proporção menor de
    comentários positivos (37% contra 55%) e alcance médio menor.
  - Maior variação isolada: `marcosrocha2oficial` sobe da 26ª para a 12ª posição, por ter 100% de comentários positivos, apesar de
    volume bruto quase nulo.
- **Diagnóstico de tabela** (`notebooks/diagnostico_medallion/gold_nsm.ipynb`, execução salva): sem duplicata por `inputUrl` e
  sem nulos; 3 perfis com NSM extremo (mais de 1,5 desvio-padrão), nenhum deles com poucos comentários (mediana de comentários
  totais 93): `tarcisiogdf` (NSM 20.633,23; 103 comentários; 55,34% positivos), `romeuzemaoficial` (16.892,99; 334; 36,53%) e
  `raquellyraoficial` (16.448,07; 263; 81,75%). Estes valores são consistentes com a ADR 0020.
- Testes automatizados da fórmula e da inversão de ranking com dado sintético: `tests/test_nsm_scorer.py`.
- Não há, nas fontes, validação de que o ranking por NSM reflete melhor a qualidade percebida do que o ranking bruto; a
  verificação mostra que **muda**, não que é **melhor**. Não registrado.

## Limitações

- O "alcance" é um proxy de intensidade de engajamento por publicação, não alcance ou impressões; deve ser declarado sempre que
  a métrica for consumida (docstring de `nsm_scorer.py`; `CONTEXT.md`).
- Herda todas as limitações do classificador de sentimento (treinado em tweets; sem validação registrada), ver
  [sentimento.md](sentimento.md).
- Instável com poucos comentários: um NSM alto sustentado por poucos comentários é um extremo estatístico, não
  necessariamente engajamento qualificado real (nota de interpretação do notebook). O NSM em si não impõe piso de comentários
  (o piso de 30 da ADR 0038 vale para os cartões de aprovação e rejeição).
- A verificação de 2026-09-19 usou só comentários de reels; os comentários de posts entram depois (ADR 0034), então os números
  da ADR 0020 não são mais os atuais.
- Mede posição relativa no grupo de governadores (min-máx), não desempenho absoluto.
- A coleta não captura compartilhamentos nem salvamentos (ADR 0018).
- Em substituição parcial: a ADR 0040 troca o **Comparativo vs. mediana** pela Tendência (decisão em avaliação, ver
  [tendencia.md](tendencia.md)). A NSM em si não muda, mas a seta do comparativo no cartão pode mudar.

## Vínculos

- Código: [`src/features/gold/nsm_scorer.py`](../../src/features/gold/nsm_scorer.py), [`src/features/gold/engagement_aggregator.py`](../../src/features/gold/engagement_aggregator.py), [`src/modeling/orchestration.py`](../../src/modeling/orchestration.py), [`dashboard/core/data.py`](../../dashboard/core/data.py) (`load_nsm`)
- ADR: [0020](../adr/0020-alinhamento-tcc-funil-cobra-race-nsm-ice-cmgr-e-reformulacao-do-dashboard-de-growth.md) (Ficha 5 e verificação com dado real), [0021](../adr/0021-dashboard-organizado-por-decisao-com-funil-como-tela-dedicada.md), [0033](../adr/0033-comparativo-vs-mediana-no-nsm-rankings-completos-com-rolagem-e-engage-sempre-comparado.md), [0018](../adr/0018-realinhar-engajamento-e-matriz-de-quadrantes-ao-relatorio-vhl-sem-produto-deputados.md), [0034](../adr/0034-pipeline-ponto-unico-ugc-no-extrator-comentarios-de-posts-janela-e-relatorio.md)
- Notebooks: [`gold_nsm.ipynb`](../../notebooks/diagnostico_medallion/gold_nsm.ipynb)
- TCC (capítulo/seção): a preencher (a ADR 0020 prevê o contraste "bruto vs. qualificado" no Cap. 6)
