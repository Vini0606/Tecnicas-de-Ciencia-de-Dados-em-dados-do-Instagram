# Tecnicas de NLP em dados do Instagram

Pipeline Medallion (Bronze/Silver/Gold em Delta Lake) que coleta, modela e apresenta métricas de
engajamento, sentimento e tópicos dos perfis de Instagram de governadores brasileiros, entregue como
um dashboard Streamlit de growth para analistas de assessoria.

## Language

**Tela**:
Uma página do dashboard organizada em torno de uma única decisão do analista de assessoria ("o que
eu posto a seguir?"), não em torno de uma tabela ou técnica de modelagem.
_Avoid_: Página, aba, view (quando falando do produto ao usuário final; "página"/`pages/` ainda é
termo técnico válido para arquivos Streamlit).

**Sub-aba**:
Divisão interna de uma Tela (ex.: NSM, Funil e Scorecard dentro do Resumo). Distinta de Tela, que é item
da navegação lateral.
_Avoid_: Tela (para algo interno a outra Tela), aba solta (ambíguo).

**Comparativo vs. mediana**:
Seta ▲/▼ que compara o valor do governador selecionado com a mediana dos demais governadores (no Funil,
em percentual; no NSM, em pontos do índice). Em "Todos" no NSM, compara a média do grupo com a mediana do
grupo e indica assimetria, não desempenho. Distinta de SUBIU/CAIU, que compara posições de ranking.
_Avoid_: Projeção, tendência (não há comparação no tempo).

**Pauta**:
Assunto de um conteúdo publicado (legenda de reel/post) agrupado pelo modelo de tópicos de discurso e
rotulado após refino. É a unidade da fila de "O que produzir": mede quanto comentário positivo os
conteúdos daquele assunto receberam. Cada reel pertence a uma única pauta (a da legenda).
_Avoid_: Tema (ambíguo com grupo de comentários), tópico (termo técnico do BERTopic).

**Grupo de comentários**:
Conjunto de comentários parecidos entre si, agrupados pelo modelo de tópicos de comentário. Descreve o
que o público diz, não o que o conteúdo trata. Exibido em "Maiores grupos de comentários", separado em
positivos e negativos, no escopo do governador selecionado.
_Avoid_: Tema, pauta (reservado ao assunto do conteúdo).

**Origem do comentário**:
A publicação em que um comentário foi feito: `reel` ou `post` (de feed). Os comentários de cada origem
ficam em tabelas Silver separadas (`comments_clean` e `post_comments_clean`) e convivem em
`governor_sentiment` pela coluna `origem_comentario` (ver ADR 0033). Um comentário capturado nas duas
origens (reel que também aparece no grid de posts) conta uma vez, como `reel`.
_Avoid_: Fonte (reservado a comentario/legenda/transcricao em `governor_sentiment`), tipo.

**Frase de decisão** (faixa de decisão / decision band):
A frase em destaque no topo de cada tela, numa faixa colorida por semáforo, que responde
"e agora, o que eu faço?" antes de qualquer gráfico. Sempre a primeira coisa lida na tela.
_Avoid_: Título, headline, insight.

**Grupo de desempenho**:
Rótulo de negócio para um cluster de conteúdo ou de perfil (ex.: "curto, converte"; "alto alcance,
baixa conversão"). O rótulo é curado a partir do perfil real do cluster, nunca o ID numérico bruto —
`cluster_label == -1` (ruído do DBSCAN) vira "casos atípicos / virais", nunca aparece como "-1".
Exceção: na análise de reels de "Comparar perfis" o analista escolhe entre "Cluster 1", "Cluster 2"… (numerados
por tamanho, nunca pelo id bruto), cada um com nome e descrição curados, sempre sob o selo "agrupamento
experimental".
_Avoid_: Cluster (termo técnico; só aparece na interface na análise de reels de "Comparar perfis", numerado).

**Selo de prioridade**:
Classificação em 3 faixas (Alta / Média / Cuidado) de uma pauta na fila de "O que
produzir", derivada dos tercis do Score ICE sobre o ranking GLOBAL de pautas (todos os perfis
combinados) — nunca recalculada só sobre as pautas do governador selecionado, para não oscilar
artificialmente quando ele tem poucas pautas próprias (ver ADR 0028). Filtrável por um controle de
botões (1 faixa ativa por vez, ou "Todas") acima da fila. Nunca exibe o score bruto por trás do selo.
_Avoid_: Score, Score ICE (métrica técnica interna — o selo é o que aparece na interface).

**Selo de confiabilidade**:
Marcação discreta ("em validação", "ilustrativo — histórico curto", "agrupamento experimental",
"piloto") que acompanha uma métrica cuja confiabilidade ainda não foi totalmente estabelecida contra
dado real. Nunca cosmético — é o que distingue esta ferramenta de um gerador de números falsamente
precisos (ver ADR 0021, Parte 4 da especificação de origem).
_Avoid_: Badge, tag, aviso genérico.

**Estágio** (do funil COBRA-RACE):
Um dos quatro momentos da jornada do público mapeados no dashboard: Reach·Alcançar,
Act·Consumir, Convert·Contribuir, Engage·Criar. Cada tela do dashboard carrega um rótulo de estágio
discreto no cabeçalho, mesmo fora da sub-aba Funil do Resumo.
_Avoid_: Etapa, fase, nível (usar "estágio" para RACE; "nível" é o termo do framework COBRA
subjacente, ambos coexistem no rótulo "Estágio · Nível").

**Gargalo**:
O estágio do funil com a menor taxa de passagem entre execuções, entre os estágios que têm dado real
(Convert→Engage é exibida, mas nunca é gargalo: compara comentários com posts de UGC de
terceiros, outra unidade e outra população — ver "Visualizações" vs. "alcance"). Marcado com o selo "gargalo" no
selo de conversão da sub-aba Funil do Resumo.
_Avoid_: Bottleneck, ponto fraco.

**Visualizações** (Reach real):
Soma de `videoPlayCount` (views reais dos Reels) usada exclusivamente no estágio Reach da sub-aba
Funil. Um dado real coletado do Instagram — diferente de "alcance", que é sempre uma estimativa.
_Avoid_: Alcance (reservado para a métrica estimada, ver abaixo) — os dois nunca são a mesma coisa
nem usam o mesmo rótulo em nenhuma tela.

**Alcance** (estimado por engajamento):
Proxy de alcance usado por NSM e Score ICE, calculado a partir de engajamento (curtidas + respostas),
porque o Instagram não expõe alcance real para essas métricas. Sempre acompanhado do tooltip
"estimativa baseada em engajamento".
_Avoid_: Reach, visualizações, views (reservados para o dado real do funil, ver acima).

**Escore composto** (Scorecard):
Nota de 0 a 100 de cada governador, soma ponderada (pesos iguais) de cinco dimensões normalizadas
min-máx entre os perfis: Alcance, Ativação, Qualidade, Profundidade e Consistência. É relativo ao
grupo de perfis — mede posição entre pares, não desempenho absoluto. Alcance usa "reproduções" (plays),
nunca "visualizações únicas". Uma dimensão sem dado suficiente fica "pendente" e o escore usa as demais, com
pesos iguais renormalizados.
_Avoid_: Índice (genérico), ranking (o ranking é a ordenação pelo escore, não o escore).

**CMGR de engajamento** / **CMGR de audiência**:
Duas taxas compostas mensais distintas. A de engajamento mede a tendência do engajamento médio por post
ao longo dos meses de publicação (base da dimensão Consistência do Escore composto). A de audiência mede o
crescimento de seguidores entre coletas e hoje está pendente por histórico insuficiente. Nunca chamar a de
engajamento de "crescimento de audiência" (ver ADR 0030). Enquanto o histórico de publicação for curto, o CMGR
de engajamento fica "pendente" e a Consistência não entra no escore.
_Avoid_: CMGR sozinho (ambíguo entre os dois).

**Engajamento qualificado** (rótulo de usuário para NSM/North Star Metric):
Nome exibido ao analista de assessoria para a NSM — comentários positivos sobre comentários totais,
ponderado pelo alcance-proxy. Na sub-aba NSM aparece como índice de 0 a 100 (min-máx entre os perfis),
contrastado com o ranking por engajamento bruto (total de curtidas e comentários). Validada contra os 27 perfis reais (ADR 0020, verificação de
2026-09-19): o ranking por NSM muda de posição para 25 dos 27 perfis frente ao ranking por
engajamento bruto — deixou de levar o selo "em validação" no dashboard.
_Avoid_: NSM (sigla técnica, nunca aparece sozinha na interface do usuário final; ok em código/ADR).
