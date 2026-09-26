---
status: accepted
---

# Filtro de prioridade, coluna de quantidade de comentários e popup de comentários por tema na fila de "O que produzir"

## Contexto

A fila de temas priorizados na Tela 2 ("O que produzir", ver docstring de `dashboard/screens/
produzir.py`, issue #112) hoje exibe 3 colunas -- Tema, % positivo, Prioridade -- construídas por
`_fila_prioridade()`: `topic_priority_score` (ranking GLOBAL de temas de comentário, todos os 27
perfis combinados) restrito às linhas cujo `Topic` aparece nos comentários do governador
selecionado, mas com `score` e `proporcao_sentimento_positivo` mantidos GLOBAIS -- decisão já tomada
na issue #112 para não recalcular o Score ICE por perfil (ver docstring do módulo) nem deixar o selo
de prioridade (tercis sobre `score`) oscilar artificialmente para governadores com poucos temas
próprios.

O usuário pediu, numa sessão de `/grilling`, 3 mudanças sobre essa mesma fila: (1) transformar a
coluna Prioridade num filtro; (2) adicionar uma coluna de quantidade de comentários do tema; (3)
abrir um popup com os comentários do tema ao clicar numa linha. O grilling resolveu a ambiguidade
central das 3 mudanças juntas: quantidade de comentários e o conteúdo do popup deveriam refletir só
os comentários do governador selecionado, ou o mesmo escopo GLOBAL já usado por `score`/`% positivo`?
Optou-se por manter GLOBAL, pelo mesmo motivo da decisão original da issue #112 (consistência entre
as colunas da mesma linha) -- `topic_priority_score` já grava `n_comentarios` por tópico
(`src/features/gold/topic_priority_scorer.py::_RESULT_COLUMNS`), então a nova coluna não exige
nenhum agrupamento novo, só expor uma coluna que já existe na tabela Gold.

`governor_sentiment` (fonte dos comentários para o popup) tem `text`, `ownerUsername`, `likesCount`,
`repliesCount`, `timestamp`, `sentiment_label`, além de `Topic`/`Name` (`GOLD_SENTIMENT_SCHEMA`,
`src/schemas_delta.py`). Nenhuma tela do dashboard hoje exibe `ownerUsername` de um comentário
individual -- o popup é o primeiro lugar a fazer isso.

Streamlit 1.55 (versão instalada, ver `pyproject.toml`) tem `st.segmented_control`, `st.dialog` e
`st.dataframe(..., on_select="rerun", selection_mode="single-row")` disponíveis e estáveis.

## Decisão

**Filtro de prioridade:** `st.segmented_control(selection_mode="single")` acima da fila, com opções
"Todas" (default) / Alta / Média / Cuidado. Filtra só as linhas exibidas na tabela -- é puramente uma
lente de visualização, sem efeito colateral em nenhum outro cálculo da tela.

**Coluna Prioridade:** continua na tabela mesmo depois do filtro virar um controle separado --
necessária no estado "Todas", onde o filtro sozinho não diz o selo de cada linha.

**Nova coluna "Comentários":** `n_comentarios` de `topic_priority_score`, GLOBAL (mesmo escopo de
`score`/`% positivo`, nunca recalculada só sobre os comentários do governador selecionado). Ordem
final da tabela: Tema | Comentários | % positivo | Prioridade.

**Recomendação principal (`decision_band`):** sem mudança. Continua baseada no topo da fila completa
(`_topico_prioritario_ajustado`), ignorando o filtro de prioridade -- fora de escopo desta ADR
(usuário sinalizou que vai revisitar essa lógica separadamente).

**Popup de comentários:** clique numa linha da fila (`st.dataframe(..., on_select="rerun",
selection_mode="single-row")`) abre um `@st.dialog` com uma tabela dos comentários GLOBAIS daquele
tema (`governor_sentiment`, `fonte == "comentario"`, `Topic` igual ao da linha clicada, todos os 27
perfis). Colunas: `text`, `sentiment_label`, `likesCount`, `repliesCount`, `ownerUsername`,
`timestamp`. Limitado aos 50 comentários com maior engajamento (`likesCount + repliesCount`),
ordenados decrescente -- sem paginação.

**Processo de entrega:** esta ADR primeiro, depois 2 issues no GitHub (`ready-for-agent`, via
`mattpocock-skills:to-spec`), cada uma via TDD e `/code-review` Standards+Spec antes do merge:
1. Filtro de prioridade + coluna "Comentários" na fila (mudança pequena, mesma função
   `_fila_prioridade`).
2. Popup de comentários por tema ao clicar na linha (peça isolada -- novo `st.dialog`, nova consulta
   de dado bruto de `governor_sentiment`).

## Por que

- Escopo GLOBAL para quantidade de comentários e popup: consistência com a decisão já tomada na
  issue #112 para `score`/`% positivo` da mesma linha -- misturar um escopo por-governador só na
  coluna nova faria 3 colunas da mesma linha responderem "de quem?" de formas diferentes sem nenhuma
  pista visual disso. `n_comentarios` já existe pronto em `topic_priority_score`, então essa escolha
  também é a que não exige nenhum agrupamento novo sobre `governor_sentiment`.
- Filtro como controle separado (não substitui a coluna): a coluna Prioridade sozinha, sem filtro,
  não deixava a analista restringir a visão para só "Alta" por exemplo; o filtro sozinho, sem a
  coluna, esconderia o selo das linhas quando "Todas" estiver selecionado -- as duas formas juntas
  cobrem os dois usos.
- `st.segmented_control` de seleção única (não multiselect/pills multi): usuário pediu explicitamente
  um "filtro de botões" com só 1 ativo por vez -- um alternador entre "Todas" e uma faixa por vez,
  nunca uma combinação de 2 faixas.
- Filtro não recalcula `decision_band`: a frase de decisão recomenda o próximo tema a produzir,
  cruzando prioridade com discurso já coberto (`_topico_prioritario_ajustado`) -- deixar um filtro de
  visualização da tabela mudar essa recomendação misturaria uma escolha de UI da analista com a lógica
  de recomendação em si. Fora de escopo por pedido explícito do usuário, que vai revisitar essa lógica
  à parte.
- `st.dialog` (modal) em vez de `st.expander` inline: usuário pediu explicitamente algo "parecido com
  um popup" -- um modal sobre a tela é a interpretação mais direta disso no Streamlit 1.55.
- Colunas completas no popup (incluindo `ownerUsername`/`timestamp`): decisão explícita do usuário
  mesmo após a ressalva de que é a primeira tela a expor autor de comentário individual -- registrado
  aqui para não ser "corrigido" sem essa mesma conversa no futuro.
- Top-50 por engajamento, sem paginação: um tema popular pode ter centenas/milhares de comentários
  globais; renderizar tudo sem corte arriscaria travar o navegador dentro de um modal. Ordenar por
  engajamento (não por data) prioriza os comentários mais visíveis/relevantes, coerente com o resto da
  tela (`Alcance` = proxy por engajamento, ver `CONTEXT.md`).
- 2 issues em vez de 1: o popup é uma peça isolada (dado bruto novo, componente novo `st.dialog`) frente
  à mudança pequena de filtro+coluna sobre uma função já existente (`_fila_prioridade`) -- PRs menores e
  revisáveis separadamente, mesmo padrão de commits pequenos do resto do projeto.

## Opções consideradas

- **Quantidade de comentários e popup restritos aos comentários do governador selecionado** --
  rejeitada: divergiria do escopo GLOBAL já usado por `score`/`% positivo` na mesma linha da fila,
  sem nenhuma pista visual da diferença de escopo entre colunas.
- **`st.multiselect`/`st.pills(selection_mode="multi")`** (filtro combinando várias faixas de
  prioridade ao mesmo tempo) -- rejeitada: usuário pediu explicitamente um alternador de 1 botão por
  vez, não uma combinação.
- **Remover a coluna Prioridade da tabela** (já que virou filtro) -- rejeitada: no estado "Todas" a
  analista perderia a única pista visual do selo de cada linha sem filtrar uma faixa de cada vez.
- **Filtro de prioridade também recalculando `decision_band`** -- rejeitada por pedido explícito do
  usuário, que prefere revisitar a lógica de recomendação principal separadamente.
- **`st.expander` inline em vez de `st.dialog`** -- rejeitada: não é visualmente um popup, só uma
  seção que expande na própria página.
- **Colunas reduzidas no popup** (`text`, `sentiment_label`, `likesCount`, `repliesCount`, sem
  `ownerUsername`/`timestamp`) -- levantada pela ressalva de exposição de identidade do autor do
  comentário, mas rejeitada pelo usuário: quer todas as colunas disponíveis.
- **Popup sem corte de volume** (mostrar todos os comentários do tema) -- rejeitada: temas muito
  debatidos podem ter volume alto o suficiente para pesar a renderização dentro de um modal.
- **Top-20 ou top-100** (em vez de top-50) -- rejeitadas: 20 corre risco de deixar de fora comentários
  relevantes de temas muito debatidos; 100 exige rolagem pesada dentro do modal, reduzindo boa parte
  da vantagem de um popup rápido de ler.
- **1 issue única cobrindo as 3 mudanças** -- rejeitada: misturaria uma mudança pequena de UI
  (filtro+coluna sobre função já existente) com uma feature nova mais arriscada (popup com dado bruto
  e componente novo) no mesmo PR.

## Consequências

- `dashboard/screens/produzir.py`: `_COLUNAS_FILA`/`_fila_prioridade()` passam a incluir
  `n_comentarios`; `render()` ganha o `st.segmented_control` acima da fila, a nova coluna
  "Comentários" na tabela exibida, a captura de seleção de linha via `st.dataframe(on_select=
  "rerun", selection_mode="single-row")`, e uma nova função pura (ex.: `_comentarios_do_tema`) que
  filtra `governor_sentiment` por `Topic`, ordena por `likesCount + repliesCount` decrescente e corta
  em 50 -- chamada de dentro de um `@st.dialog` novo.
- `tests/test_dashboard_screens_produzir.py` ganha casos para: `n_comentarios` propagado corretamente
  em `_fila_prioridade`, filtro de prioridade sobre a tabela exibida, e a nova função de seleção/corte
  de comentários por tema (vazio, menos de 50, mais de 50, empate de engajamento).
- `CONTEXT.md` ganha o termo "Selo de prioridade", formalizando um rótulo que já existia em código
  (`SELO_ALTA`/`SELO_MEDIA`/`SELO_CUIDADO`) mas nunca tinha entrada no glossário.
- Primeira tela do dashboard a exibir `ownerUsername` de um comentário individual -- qualquer decisão
  futura de mascarar/anonimizar autor de comentário precisa revisitar este popup também, não só telas
  novas.
- Nenhuma mudança em `topic_priority_scorer.py` nem em `governor_sentiment`/`topic_priority_score`
  (Gold) -- as 3 mudanças são só de leitura/exibição sobre dado já existente.
