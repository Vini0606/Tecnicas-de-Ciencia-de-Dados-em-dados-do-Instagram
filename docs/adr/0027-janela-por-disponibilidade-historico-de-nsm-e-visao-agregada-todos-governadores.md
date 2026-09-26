---
status: accepted
---

# Janela de comparação por disponibilidade de dado (não calendário), histórico de NSM e visão agregada "Todos os Governadores"

## Contexto

Sessão de `/grill-with-docs` a partir de um pedido do usuário de 5 ajustes no Resumo (Tela 1): mover os
filtros da seção "Evidência histórica de desempenho" para a direita do gráfico (25% da largura),
adicionar delta aos KPIs "Engajamento qualificado" (NSM) e "% positivo", investigar por que os KPIs de
"Crescimento" não aparecem, remover a legenda que fica abaixo da faixa de decisão, e adicionar uma opção
"Todos os Governadores" no seletor de governador.

Levantamento contra o código e o dado real (nesta sessão) encontrou que 3 dos 5 itens já eram esperados
ou já tinham causa raiz conhecida, não bugs novos:

1. **KPIs de Crescimento "não aparecem"**: `governor_growth_metrics` simplesmente não existia em
   `data/gold/` -- `scripts/run_growth_metrics.py` é standalone (ADR 0020, Ficha 7) e nunca tinha sido
   executado. Resolvido nesta sessão rodando o script (26 perfis, todos "ilustrativo" -- esperado, pouco
   histórico acumulado ainda). Não é uma decisão desta ADR, só uma lacuna operacional fechada.
2. **NSM sem seta de variação**: `resumo.py` já computa e exibe o delta do NSM exatamente como os outros
   KPIs (mesmo padrão de `kpi_row`) -- mas `dashboard/core/data.py::load_nsm_history()` sempre retorna
   vazio, porque `NsmScorer.write` grava `governor_nsm` em modo `overwrite`, sem nunca escrever
   `governor_nsm_history`. A ADR 0025 já previu e adiou essa mudança de pipeline explicitamente
   ("fora do escopo desta issue").
3. **"% positivo" sem seta de variação na maioria dos governadores**: medido contra o dado real de
   `governor_sentiment_history` -- de 25 governadores com comentários, só **7** têm delta calculável;
   os outros 18 têm dado na janela atual de `JANELA_ALERTA_NEGATIVIDADE_DIAS` (7) dias corridos, mas
   ZERO dado nos 7 dias corridos imediatamente anteriores. `compare_publication_window` (ADR 0025) ancora
   em calendário (a maior data disponível menos N dias), não em disponibilidade real de dado -- a mesma
   premissa de fundo que motivou a ADR 0021 (pipeline sem cadência fixa) e a ADR 0025 (execução vs.
   publicação) se aplica de novo aqui, uma camada mais fundo: mesmo comparando por PUBLICAÇÃO em vez de
   por EXECUÇÃO, uma janela de calendário fixa ainda assume uma cadência de postagem que a maioria dos
   governadores não tem.

Os outros 2 itens (mover filtro para 25% à direita do gráfico; remover a legenda "Engajamento, seguidores
e NSM comparam..." abaixo da faixa de decisão) são ajustes de UI diretos, sem decisão de modelo de domínio
por trás -- implementados junto, sem entrada própria nesta ADR.

## Decisão

**1. `compare_publication_window` (`dashboard/core/deltas.py`) muda de janela por CALENDÁRIO para janela
por DISPONIBILIDADE de dado.** Em vez de "últimos N dias corridos vs. os N dias corridos anteriores"
(ancorado na maior data disponível), passa a ser "últimos N dias de publicação COM pelo menos 1 linha de
dado vs. os N dias de publicação com dado imediatamente anteriores a esses" -- ignora buracos de coleta
sem limite de tamanho. `janela_anterior` vazia (delta `None`) só acontece agora quando não existe
NENHUM dia anterior com dado, não mais quando o buraco entre coletas excede N dias corridos -- caso hoje
raro (só o primeiro dado coletado de um governador cairia nesse caso). **Janela assimétrica aceita
deliberadamente:** se a janela anterior tiver MENOS dias-com-dado do que a janela atual (histórico ainda
fino -- ex.: 7 dias atuais vs. só 1 dia anterior disponível), o delta é calculado e exibido mesmo assim,
sem um piso mínimo de dias -- prioriza sempre mostrar uma seta de variação (aceitando que ela fique mais
ruidosa em histórico curto) a esconder a comparação, mesmo risco/critério já aceito pela ADR 0026 para
CMGR/retenção "ilustrativo" em vez de ocultos. Função compartilhada por Resumo
(`% positivo`) e Radar (`_tema_maior_alta_negatividade`, critério PRINCIPAL de alerta) -- os dois ganham o
comportamento novo automaticamente, sem duplicar lógica. `N` continua `JANELA_ALERTA_NEGATIVIDADE_DIAS`
(default 7, configurável via `.env`), sem mudança de valor.

**2. `NsmScorer` passa a gravar `governor_nsm_history` em modo `append`, além de `governor_nsm`
(`overwrite`, como hoje).** Mesmo padrão de `EngagementHistoryAggregator`/`governor_engagement_history`:
uma linha por perfil por execução, sob o mesmo `run_id`/`_generated_at` já usados em `governor_nsm`.
Fecha a lacuna que a ADR 0025 previu e adiou -- `dashboard/core/data.py::load_nsm_history()` e
`compare_vs_historical_average` já existem e não mudam, só passam a receber dado real. NSM ganha seta de
variação no Resumo assim que a próxima execução de modelagem rodar (a tabela `_history` começa vazia
igual às outras -- precisa de pelo menos 2 execuções acumuladas para o primeiro delta aparecer, mesmo
critério de `compare_vs_historical_average` para as demais métricas de perfil).

**3. Nova opção "Todos os Governadores" no seletor de governador do Resumo.** Ao ser selecionada, os 4
KPIs da 1ª linha, os 2 KPIs de Crescimento e o gráfico de "Evidência histórica de desempenho" deixam de
filtrar por um `inputUrl` e passam a agregar sobre TODOS os governadores disponíveis, com a mesma
estrutura de tela (mesmos KPIs, mesmo gráfico, mesma faixa de decisão) -- **agregação simples**:

- **Métricas de contagem** (Seguidores; Quantidade de publicações e as somas de Curtidas/Comentários/
  Visualizações no gráfico de evidência): **soma** entre governadores.
- **Métricas de proporção/taxa** (% engajamento, % positivo, NSM, CMGR, retenção): **média simples**
  entre governadores (não ponderada por volume -- cada governador pesa igual, mesmo espírito de
  "Comparar perfis" já não ponderar por seguidores). Para NSM especificamente, isso significa que um
  perfil com poucos comentários pesa exatamente igual a um perfil com milhares -- **confirmado
  deliberadamente**, consistente com a agregação simples escolhida para as demais métricas de
  proporção; não pondera por volume de comentários.
- **Deltas**: computados sobre a MESMA série agregada (ex.: soma de seguidores por `_run_id` em vez de
  seguidores de 1 governador por `_run_id`, depois `compare_vs_historical_average` de novo sobre essa
  série sintética) -- reaproveita as primitivas de `deltas.py` sem duplicar lógica de comparação, só muda
  o que entra nelas antes de chegar lá.
- **Risco aceito -- cobertura de governadores varia entre execuções.** `governor_engagement_history`
  nem sempre tem todos os governadores presentes em toda `_run_id` (perfil sem Instagram rastreável,
  falha pontual de coleta, etc.). Somar `Seguidores` por execução sem alinhar o conjunto de governadores
  entre a execução atual e o histórico pode fazer o agregado subir/cair só porque o NÚMERO DE PERFIS
  reportando mudou, não porque houve crescimento/queda real de audiência. Risco aceito conscientemente
  (não filtra por cohort fixo) -- registrado aqui para não ser confundido depois com um bug.
- **Confiabilidade agregada de CMGR/Retenção -- sempre mostra a proporção, nunca esconde nem exclui.**
  O rótulo agregado nunca ganha automaticamente o sufixo "· ilustrativo" nem exclui governadores
  `confiavel=False` da média -- SEMPRE a média de todos os governadores disponíveis, com o tooltip
  declarando explicitamente a proporção confiável (ex.: "18 de 26 perfis com histórico confiável; os
  demais ainda são ilustrativos"). Hoje (2026-09) essa proporção seria "0 de 26" -- toda a base ainda é
  ilustrativa (ver Contexto, item 1) -- então o comportamento só passa a diferenciar governadores entre
  si conforme mais execuções se acumularem.
- **Frase de decisão**: mesma lógica (`_nivel_semaforo`) sobre os deltas agregados -- sem tela nem regra
  nova, só um `governor_url` especial (sentinela, não uma URL real) que os `_filtrar_por_governador`/
  `_delta_*_para_governador` tratam como "não filtrar, agregar tudo".
- Fora de escopo: qualquer coisa além do Resumo (Radar, Produzir, Comparar, Discurso×Reação, Funil
  continuam exigindo 1 governador selecionado) -- decisão de produto separada, se fizer sentido no
  futuro.

**4. Filtros da "Evidência histórica de desempenho" migram para a direita do gráfico, coluna de 25% da
largura** (`st.columns([0.75, 0.25])`) -- tipo de conteúdo, métrica e período, empilhados verticalmente
na coluna direita; o gráfico ocupa a coluna esquerda (75%).

**5. Remove a legenda `st.caption(...)` que hoje fica logo abaixo da faixa de decisão do Resumo**
("Engajamento, seguidores e NSM comparam contra a média histórica de execuções...") -- sem substituto;
a explicação de metodologia por trás de cada delta continua disponível via tooltip (`help_text`) de cada
KPI individual.

**Processo de entrega:** mesmo padrão das ADRs 0019/0020/0021/0023/0024/0025/0026 -- implementação via
TDD e `/code-review` Standards+Spec antes do merge.

## Por que

- Janela por disponibilidade em vez de calendário: o problema de fundo (pipeline sem cadência fixa) já
  motivou trocar EXECUÇÃO por PUBLICAÇÃO na ADR 0025 -- mas um corte de calendário fixo sobre a data de
  publicação ainda assume que o AUTOR do post posta com uma cadência mínima, o que 18 dos 25 governadores
  medidos hoje não têm. Comparar por "N dias com dado" em vez de "N dias corridos" resolve a mesma classe
  de problema, na mesma direção já estabelecida, sem inventar um conceito novo.
- NSM history mirror do padrão de engagement_history: menor risco -- reaproveita um padrão já validado em
  produção (`EngagementHistoryAggregator`) em vez de desenhar um novo.
- "Todos os Governadores" com agregação simples (soma/média não ponderada), não um novo tipo de tela:
  mantém a estrutura fixa da ADR 0021 (decisão → KPIs → prova) intacta -- o usuário troca só o que está
  filtrado, não aprende uma tela nova.
- Escopo restrito ao Resumo: é a única tela hoje com KPIs agregáveis de forma direta (contagens e taxas
  simples); Radar/Produzir/Discurso×Reação/Funil dependem de estruturas por governador (tópicos, clusters,
  funil) que não têm uma agregação óbvia de "todos juntos" sem uma conversa de produto própria.
- Remover a legenda de metodologia: informação duplicada -- cada KPI já carrega a mesma explicação via
  tooltip individual (`help_text`), então a legenda solta abaixo da faixa de decisão só ocupa espaço sem
  acrescentar contexto que o usuário não tenha já a 1 hover de distância.
- Janela assimétrica aceita sem piso mínimo: mesmo critério de "nunca esconder dado por omissão" já usado
  em `_nivel_semaforo`/`week_over_week` desde a ADR 0021 -- prioriza mostrar uma seta possivelmente
  ruidosa a mostrar nenhuma, na mesma linha do achado desta sessão (18 de 25 governadores hoje ficavam
  sem seta nenhuma).
- Confiabilidade agregada por proporção no tooltip (nunca por exclusão nem por sufixo automático):
  qualquer regra binária (tudo ilustrativo se 1 for; excluir quem não é confiável) esconderia informação
  real -- a primeira mascara progresso real conforme mais governadores ficam confiáveis, a segunda
  mascara que "Todos os Governadores" às vezes representa menos do que os 26/27 perfis completos.

## Opções consideradas

- **Aumentar a janela fixa de calendário (ex.: 30 dias) em vez de mudar para disponibilidade** --
  rejeitada pelo usuário: reduz mas não elimina o problema, e a métrica fica menos "recente" sem resolver
  a causa raiz (cadência de postagem desigual entre governadores).
- **Manter janela de calendário como está** -- rejeitada: deixaria a maioria dos governadores
  permanentemente sem seta de variação em "% positivo" e no critério principal do Radar.
- **"Todos os Governadores" com média ponderada por volume/seguidores** -- não escolhida: o usuário pediu
  "agregado simples"; ponderação fica para uma iteração futura se a média simples se mostrar enganosa na
  prática (ex.: 1 governador com poucos comentários pesando igual a outro com milhares).
- **Adicionar "Todos os Governadores" em todas as 6 telas** -- rejeitada por escopo: as outras 5 telas não
  têm uma agregação natural (comparação de pares, funil, tópicos de discurso), decisão de produto maior.
- **Janela anterior com piso mínimo de N dias** (só mostra delta se ambas as janelas tiverem >= N dias
  com dado) -- rejeitada pelo usuário: reduz o ruído em histórico fino, mas reintroduz o problema
  original (governador sem seta) só que com um gatilho mais raro, em vez de resolvê-lo.
- **Confiabilidade agregada "qualquer um ilustrativo contamina todos"** ou **"excluir não-confiáveis da
  média"** -- ambas rejeitadas: a primeira mantém o rótulo "ilustrativo" por tempo desproporcional (1
  perfil atrasado já contamina os outros 25); a segunda esconde quantos perfis realmente entram na conta.
  Proporção sempre visível no tooltip (opção escolhida) informa sem esconder nem subestimar.

## Consequências

- `dashboard/core/deltas.py::compare_publication_window`: reescreve a lógica de corte de janela para
  operar sobre dias distintos com dado, não sobre um intervalo de calendário -- assinatura e retorno não
  mudam, só o critério de quais linhas entram em cada janela.
- `src/features/gold/nsm_scorer.py` (`NsmScorer.write`) ganha escrita adicional de
  `governor_nsm_history` (`mode="append"`) -- mudança de pipeline, não só de dashboard;
  `src/repositories/delta_repository.py::load_nsm_history` não muda.
- `dashboard/screens/resumo.py`: seletor de governador ganha uma opção sentinela "Todos os Governadores";
  toda a lógica de filtro/agregação por governador (`_filtrar_por_governador`, os `_delta_*_para_governador`)
  precisa de um caminho de agregação alternativo; layout da seção de evidência muda para
  `st.columns([0.75, 0.25])`; a legenda abaixo da faixa de decisão é removida.
- `dashboard/screens/radar.py`: nenhuma mudança de código própria, mas o comportamento de
  `_tema_maior_alta_negatividade` muda (janela por disponibilidade) por reaproveitar a mesma função de
  `deltas.py` -- testes de `tests/test_dashboard_screens_radar.py` que assumem janela de calendário
  precisam de casos novos.
- `tests/test_dashboard_core_deltas.py`, `tests/test_dashboard_screens_resumo.py`,
  `tests/test_dashboard_screens_radar.py`, `tests/test_nsm_scorer.py` precisam de casos novos.
