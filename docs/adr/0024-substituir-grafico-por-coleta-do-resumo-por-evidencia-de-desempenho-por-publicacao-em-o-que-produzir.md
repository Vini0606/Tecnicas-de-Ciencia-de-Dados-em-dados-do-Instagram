---
status: accepted
---

# Substituir gráfico "por coleta" do Resumo por evidência de desempenho por publicação em "O que produzir"

## Contexto

O usuário pediu uma sessão de `/grill-with-docs` para trocar o único gráfico de série temporal "por
coleta" que restava no dashboard -- "Tendência de engajamento (últimas execuções)"
(`dashboard/screens/resumo.py::_ultimas_execucoes`, `st.bar_chart` agregado por `_run_id`, rodapé da
Tela 1) -- por um gráfico por data de publicação, e depois expandir a ideia com mais métricas de
engajamento (curtidas, comentários, compartilhamentos, visualizações, quantidade de publicações).

Levantamento inicial no código confirmou que esse é de fato o único gráfico "por coleta" que sobrou: a
ADR [0023](0023-filtro-de-calendario-por-data-de-publicacao-no-radar-e-resumo.md) já migrou a linha do
tempo do Radar (Tela 3) para data de publicação; Discurso×Reação e Funil nunca tiveram gráfico de série
temporal, só comparações de tema ou deltas numéricos.

**Dado disponível:** `reels_clean` (Silver) já tem `data_hora` (publicação real), `likesCount`,
`commentsCount`, `videoPlayCount` e `Total de Engajamento`, reconstruído do zero a cada execução a partir
do Bronze inteiro (`PostCleaner.clean_reels` + `deduplicate_latest`, mode `overwrite`) -- ou seja, sempre
1 linha por post, sem necessidade de deduplicar no dashboard (diferente de `governor_sentiment_history`,
que é append-only e exigiu dedup na ADR 0023). `posts_clean` (feed, não-reel) tem schema quase idêntico
(`data_hora`, `likesCount`, `commentsCount`) mas **não tem loader em `dashboard/core/data.py` hoje** --
só reels estão conectados ao dashboard.

**Compartilhamentos:** pesquisa contra a documentação oficial dos actors Apify em uso (ver
`docs/research/apify-instagram-actors-cobra-mapping.md`, §1.2) confirmou que `apify/instagram-reel-scraper`
suporta `sharesCount` via flag paga `includeSharesCount` (plano Apify Starter+), hoje desligada; e que
`apify/instagram-post-scraper` (feed) **não expõe** `sharesCount`/`reshareCount` em nenhuma hipótese --
limitação permanente do actor, não uma lacuna de configuração. Habilitar a flag é uma decisão de custo
que só o usuário pode aprovar -- tratada à parte, fora desta ADR (issue #149, `ready-for-human`).

A conversa então evoluiu de "só trocar um gráfico" para uma pergunta maior: onde essa evidência de
desempenho por publicação deveria morar. A primeira proposta (uma 7ª tela dedicada) foi descartada por
contrariar o princípio de design da ADR
[0021](0021-dashboard-organizado-por-decisao-com-funil-como-tela-dedicada.md) -- cada tela responde a UMA
pergunta de decisão, não é organizada por tipo de dado. O usuário então identificou o encaixe certo: a
Tela 2 ("O que produzir") já tenta responder "o que devo postar a seguir?" usando só um **snapshot atual**
de `governor_clusters` (sem noção de tempo, sem posts de feed -- `_clusters_reel_do_governador` filtra só
`content_type == 'reel'`) para eleger um formato vencedor. A série temporal por publicação é exatamente a
evidência que faltava para essa recomendação ser mais completa -- o usuário pediu explicitamente para
não se prender ao princípio "scannable numa tela só" da ADR 0021 nesta tela, e responder a pergunta de
forma completa em vez de resumida.

## Decisão

**Tela 1 (Resumo):**
- Remove o gráfico de barras "Tendência de engajamento (últimas execuções)" -- sem substituto nesta tela.
- Remove o seletor "Período" do cabeçalho (hoje um stub com única opção "Última coleta").
- O filtro de calendário que já existe hoje (`st.date_input`, hoje só afeta o destaque "tema em alta de
  negatividade") sobe para o cabeçalho, no lugar do "Período" removido -- mesmo filtro, mesmo escopo de
  efeito (só o destaque de negatividade; KPIs de engajamento/seguidores continuam "vs. última coleta",
  ADR 0023 intocada nesse ponto).
- Novo 4º destaque curto ("N publicações nos últimos X dias -- ver tendência completa em O que
  produzir"), mesmo padrão de referência cruzada "Ver mais na tela Y" já usado pelos destaques 2 e 3.

**Tela 2 (O que produzir):**
- Nova seção "Evidência histórica de desempenho", **abaixo** da recomendação atual (fila de prioridade +
  cartões de formato) -- puramente aditiva: zero mudança na lógica de recomendação existente
  (`_grupo_maior_engajamento`, `_mapear_grupos_para_cartoes`, `_recomendacao_principal` continuam
  reel-only, baseadas no snapshot atual, intocadas). Reabrir esse algoritmo para consumir a série
  temporal é uma decisão de produto maior, deliberadamente adiada.
- Seletor de tipo de conteúdo: Posts / Reels / Ambos.
- Seletor de métrica: curtidas, comentários, visualizações (só produz dado quando o recorte inclui
  Reels), quantidade de publicações.
- Um gráfico de linha por vez (não uma grade fixa de 4 gráficos) -- evita mistura de escalas
  incompatíveis (quantidade de posts/dia é um número pequeno, curtidas pode ser milhares) e mantém
  consistência com o padrão visual já usado no Radar/Resumo (nunca mais de uma série por gráfico).
- Eixo X = data de publicação, quebra de linha em gap > 7 dias sem dado (mesmo critério já usado no
  Radar, ADR 0023), abre com todo o período disponível (sem corte padrão -- mesma justificativa da ADR
  0023: não há cadência de coleta previsível). Calendário próprio desta seção, independente do Resumo.
- Sem coloração de marcador por limiar de alerta -- esse recurso é específico do limiar de negatividade
  do Radar; não existe (nem faz sentido inventar agora) um "limiar de alerta" de curtidas/visualizações.

**Camada de dado:**
- Novo `load_posts_content()` em `dashboard/core/data.py`, espelhando `load_reels_content()` (lê
  `posts_clean` via `DeltaRepository.load_posts()`).
- Nova função compartilhada em `deltas.py`, generalizando o padrão de
  `aggregate_pct_negative_by_publication_day` (ADR 0023) para qualquer coluna de métrica, com dois modos
  de agregação por dia: soma (curtidas, comentários, visualizações) e contagem de linhas (quantidade de
  publicações).
- `_quebrar_em_segmentos` (quebra de linha em gap > 7 dias, hoje privada em `radar.py`) sobe para
  `deltas.py` como função compartilhada -- a nova seção de "O que produzir" é um segundo consumidor real,
  o que já justifica a extração (não havia justificativa para isso na ADR 0023, com um único consumidor).
- Posts de feed entram na nova seção de evidência (via `load_posts_content()`), mas continuam fora da
  lógica de recomendação de formato existente (que segue reel-only).

**Compartilhamentos:** fora de escopo desta ADR -- issue #149 (`ready-for-human`) trata a decisão de
custo/plano pago separadamente. Mesmo se aprovada, não haveria dado histórico retroativo (a série só
começa a existir a partir do primeiro run com a flag ligada).

**Processo de entrega:** mesmo padrão das ADRs 0019/0020/0021/0023 -- esta ADR primeiro, depois issue(s)
no GitHub (`ready-for-agent`), via TDD e `/code-review` Standards+Spec antes do merge.

## Por que

- Só um gráfico "por coleta" restava no dashboard inteiro -- confirmado por busca no código antes de
  desenhar qualquer solução, evitando resolver um problema maior do que o real.
- `reels_clean`/`posts_clean` já reconstroem do zero a cada execução (dedup por `id`, `mode=overwrite`) --
  diferente de `governor_sentiment_history` (append-only), não precisam de deduplicação extra no
  dashboard antes de agregar por dia de publicação.
- Uma 7ª tela dedicada só por tipo de dado contrariaria o princípio "cada tela responde uma decisão" da
  ADR 0021; encaixar a evidência dentro de "O que produzir" a torna parte da MESMA decisão ("o que devo
  produzir?"), não uma decisão nova.
- Opção aditiva (não integrada à lógica de recomendação) escolhida deliberadamente: entrega a evidência
  completa sem arriscar quebrar a lógica de clusterização/mapeamento DBSCAN→grupo de negócio já validada
  em produção; dá espaço para a analista comparar recomendação snapshot vs. tendência real antes de uma
  decisão maior (futura ADR) sobre se o algoritmo deveria mudar.
- Um gráfico por vez (não uma grade 2x2 fixa): resolve sozinho o caso "visualizações não existe para
  posts de feed" (mostra estado vazio só quando a combinação não tem dado, em vez de um card
  permanentemente quebrado na grade) e evita comparar métricas de escalas muito diferentes no mesmo eixo.
- Referência cruzada no Resumo ("Ver mais em O que produzir"): mantém descoberta para quem só abre a Tela
  1, mesmo padrão já usado 2x nessa tela -- custo de implementação baixo (mais uma função pura + 1-2
  linhas de `st.caption`).
- Compartilhamentos fora de escopo: é uma decisão de custo (plano pago), não uma decisão de produto do
  dashboard -- misturar as duas atrasaria a entrega da parte que já está totalmente decidida.

## Opções consideradas

- **Nova tela dedicada ("Desempenho de conteúdo")** -- rejeitada: organiza por tipo de dado, não por
  decisão, contrariando o princípio central da ADR 0021.
- **Páginas separadas por tipo de conteúdo (Posts / Reels / Combinado)** -- rejeitada pelo próprio
  usuário: fragmentaria ainda mais a navegação sem nenhum ganho sobre um seletor dentro de uma tela.
- **Integrar a série temporal à lógica de recomendação de formato** (Opção B, recomputar
  `_grupo_maior_engajamento` sobre uma janela recente em vez do snapshot completo) -- adiada
  deliberadamente: mudança de algoritmo de verdade, maior risco, melhor decidida depois de ver o uso real
  da evidência aditiva.
- **Grade fixa de 4 gráficos simultâneos** -- rejeitada: pesada (4 `plotly_chart` sempre renderizando),
  gera um card permanentemente vazio/quebrado para "visualizações" quando o recorte é só Posts.
- **Manter o gráfico de tendência (ainda que redesenhado) no próprio Resumo** -- rejeitada: o Resumo é
  "como foi minha semana" (retrospectivo, uma linha só), não o lugar certo para explorar várias métricas
  × vários recortes de conteúdo; isso é evidência de decisão, papel de "O que produzir".
- **Habilitar `sharesCount` como parte desta ADR** -- rejeitada: decisão de custo/plano pago exige
  aprovação explícita do usuário, tratada em issue separada (#149).

## Consequências

- `dashboard/screens/resumo.py`: remove `_ultimas_execucoes` e o `st.bar_chart` associado; o
  `st.selectbox` de "Período" no cabeçalho é substituído pelo `st.date_input` que hoje vive só no destaque
  de negatividade; ganha uma função pura nova para o 4º destaque ("N publicações... ver mais").
- `dashboard/screens/produzir.py`: ganha uma nova seção de renderização (seletor de tipo + seletor de
  métrica + gráfico de linha), funções puras novas testadas isoladamente -- estrutura fixa da ADR 0021
  (cabeçalho → frase de decisão → prova) continua valendo até o fim da prova atual; a nova seção é
  estritamente posterior a ela, não reordena nada existente.
- `dashboard/core/data.py` ganha `load_posts_content()`.
- `dashboard/core/deltas.py` ganha uma função de agregação por dia genérica (soma/contagem por métrica) e
  passa a exportar `_quebrar_em_segmentos` (renomeada para o vocabulário compartilhado, sem underscore de
  privado).
- `dashboard/screens/radar.py` passa a importar a quebra de segmento de `deltas.py` em vez de definir a
  própria -- refatoração mecânica, sem mudança de comportamento.
- `tests/test_dashboard_core_data.py`, `tests/test_dashboard_core_deltas.py`,
  `tests/test_dashboard_screens_resumo.py`, `tests/test_dashboard_screens_produzir.py` e
  `tests/test_dashboard_screens_radar.py` (só o import da quebra de segmento) precisam de casos novos.
- Issue #149 (`ready-for-human`) permanece bloqueada em decisão de custo do usuário, sem relação de
  dependência técnica com o trabalho desta ADR -- pode ser aprovada/implementada em qualquer ordem.
