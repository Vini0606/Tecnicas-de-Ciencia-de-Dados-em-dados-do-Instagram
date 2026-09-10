# Especificação — Dashboard como Ferramenta de Growth

**Dashboard:** Instagram Analytics — Governadores (Streamlit)
**Status:** Draft
**Complementa:** ADR 0017 (esqueleto atual), `docs/research/apify-instagram-actors-cobra-mapping.md`, plano de implementação de análises (Fichas 1-7) discutido na sessão de alinhamento TCC.

Este documento especifica o que muda nas páginas **existentes** do dashboard, além da aba nova de funil já decidida (`pages/05_funil.py`, ver seção própria). Segue o processo da skill `dashboard-specification`, adaptado à realidade do projeto (Streamlit multipage + `DeltaRepository`, não uma ferramenta de BI genérica).

---

## Propósito

**Pergunta primária que o dashboard responde:** "Como o engajamento do meu governador está crescendo, o que devo produzir a seguir, e como isso se compara aos meus pares?" — para assessorias de comunicação política que precisam decidir o que produzir, amplificar ou abandonar.

**Audiência primária:** assessor(a) de comunicação/redes sociais do governador — uso semanal/ad-hoc, conforto técnico baixo-médio (lê números e gráficos, não escreve query).
**Audiência secundária:** o próprio governador/gestão — uso esporádico, visão executiva (poucos números, alto nível).
**Frequência de uso:** semanal (rotina de conteúdo) + ad-hoc (durante picos de repercussão).

---

## Métricas novas (além das já existentes no ADR 0017)

| Métrica | Definição | Tabela Gold fonte | Estágio do pipeline | Granularidade |
|---|---|---|---|---|
| Cluster de conteúdo (feed) | Cluster PCA→AutoClusterHPO de posts do feed | `governor_clusters` (+ coluna `content_type`) | Modelagem | por post |
| Cluster de perfil | Cluster comportamental do governador (engajamento/recência/frequência) | `governor_profile_clusters_engagement` | Pós-modelagem (Fase 2) | por governador |
| Tópicos do discurso oficial | BERTopic sobre legendas+transcrições | `governor_discourse_topics` (nova) | Modelagem | por post/reel |
| North Star Metric | Engajamento positivo qualificado (comentários positivos/total, ponderado por alcance) | `governor_nsm` (nova) | Pós-modelagem (Fase 2) | por governador |
| Score ICE | Prioridade de tópico (Impacto×Confiança×Facilidade) | `topic_priority_score` (nova) | Pós-modelagem (Fase 2) | por tópico |
| CMGR / retenção | Crescimento mensal composto, calculado sobre o histórico acumulado | novo módulo sobre `governor_engagement_history`/`governor_sentiment_history` | Pós-modelagem (Fase 2) | por governador, ao longo do tempo |
| Volume/engajamento de UGC | Contagem + engajamento agregado de posts de terceiros marcando/mencionando o perfil | fonte em definição (actors Apify em experimento) | Extração (novo) | por governador, por período |

Todas seguem o padrão já estabelecido: loader próprio em `src/dashboard/loaders.py` (`load_X()`, `@st.cache_data`, `try/except FileNotFoundError → pd.DataFrame()`), lido via `DeltaRepository`, nunca Delta direto.

---

## Layout por página

### Home (`app.py`) — hoje: 4 KPIs globais (governadores, reels, comentários, % sentimento positivo) + navegação + explicação da metodologia

**Mudança recomendada:** adicionar 1 métrica de growth ao KPI row existente — **NSM médio da base** (ou "governador com maior alta de NSM no período", se histórico já existir) — para dar uma leitura executiva de "estamos crescendo com qualidade" já na entrada, sem duplicar conteúdo das páginas internas.

**Decisão em aberto (gosto, não técnica):** isso pode ser (a) mais um `st.metric` na mesma linha de 4 colunas (vira 5), ou (b) uma segunda linha de KPIs "Growth" separada da linha "Volume" atual, com um subtítulo. Recomendo (b) — separar visualmente "quanto" (volume) de "quão bem" (qualidade/growth) evita que a Home vire uma parede de números indistintos. Mas isso é preferência de produto, não bloqueia nada — decida ao implementar.

---

### `pages/01_explorar.py` — hoje: correlação livre + scatter, granularidade de PERFIL (já é a base de `tab:matriz_correlacao`)

Esta página já opera no nível de agregação certo para as duas novidades de perfil — não precisa de página nova, só enriquecer o `df_profiles` existente.

**Mudanças:**
1. Adicionar `cluster_perfil_engajamento` (via `enrich_with_profile_cluster`, **já importado e já usado nesta página** para os filtros de grupo — só falta usar a coluna no scatter) como opção de cor (`color=`) no `plot_scatter` — permite ver visualmente se o cluster de perfil se separa nas variáveis exploradas.
2. Adicionar `nsm` e `volume_ugc` (quando existirem) à lista `numeric_cols` automaticamente — não exige código novo, já que `numeric_cols` é derivado de `select_dtypes(include=np.number)`; só é preciso que o loader que popula `df_profiles_enriched` já traga essas colunas via join (mesma função `enrich_with_*` desta página).

**Não muda:** o heatmap de correlação continua livre (usuário escolhe eixos), sem curar um subconjunto — mesma filosofia já documentada em `METRICAS_COMPARACAO` de `03_performance.py` ("decisão do usuário de não curar um subconjunto").

---

### `pages/02_insights.py` — hoje: contagem de reels/comentários, top reels, sentimento (dist. + tendência), tópicos de comentários, cluster de reel, cluster de perfil (já existe, degrada bem se a tabela não existir)

Página mais afetada — é onde "discurso vs. reação" e priorização de conteúdo vivem, ao lado do que já existe.

**Mudanças, na ordem em que devem aparecer (depois de "Tópicos mais frequentes", antes de "Padrões de conteúdo dos reels"):**

1. **Nova seção "Discurso vs. Reação"** — carrega `governor_discourse_topics` (novo loader `load_discourse_topics()`, mesmo padrão degradado). Layout: duas colunas lado a lado — esquerda "Do que a assessoria fala" (top N tópicos de `governor_discourse_topics`), direita "Do que o público fala" (reaproveita o `df_topicos` que a página já calcula de `df_filtrado_comments["Name"]`). Mensagem de vazio: "`governor_discourse_topics` ainda não existe. Rode `scripts/run_modeling.py` (estágio de discurso) para gerá-la" — mesmo texto/padrão dos outros avisos desta página.
2. **Nova seção "Prioridade de Temas (o que produzir a seguir)"** — tabela de `topic_priority_score` (novo loader `load_topic_priority_score()`) ordenada por score decrescente, mostrando tópico + componentes (Impacto/Confiança/Facilidade) + score final. Esta é a "tabela top temas a produzir" que a Ficha 7 do plano associa à subseção 6.5.3 do Cap. 6 — é conteúdo de nível de BASE (todos os governadores, um ranking de tópicos de comentários agregado), não por governador individual; renderizar fora do bloco `if df_filtrado_comments.empty` atual, ou como tabela global no topo da seção.
3. **Estender "Padrões de conteúdo dos reels" → "Padrões de conteúdo (Reels e Feed)"**: com a coluna `content_type` em `governor_clusters`, trocar o `st.dataframe(...)` atual (que já agrupa por `cluster_label`) para agrupar por `["content_type", "cluster_label"]` — muda a chamada de `.groupby("cluster_label")` para `.groupby(["content_type", "cluster_label"])`, sem mudar a estrutura da página. Título ganha um `st.radio`/`st.tabs` opcional para filtrar Reels vs. Feed se o volume de linhas ficar grande.
4. **"Perfil de comportamento do governador"**: sem mudança de código — já existe e já lê `governor_profile_clusters_engagement`. Só passa a ter dado quando a Ficha 1 rodar.

---

### `pages/03_performance.py` — hoje: comparação com pares (métricas cruas), matriz de quadrantes, lacuna de execução, tendência de engajamento (auto-refresh)

**Mudanças:**
1. **NSM na comparação com pares**: adicionar `"nsm"` a `METRICAS_COMPARACAO` (linha 62-73) — reaproveita o mecanismo de ranking existente (`compute_governor_comparison`) sem código novo, só a lista de colunas.
2. **Nova seção "Engajamento Bruto vs. Qualificado"** (Ficha 5 pede explicitamente esse contraste: "contrastar o ranking por NSM com o ranking por engajamento bruto — provar que mudam de ordem"). Layout: duas colunas — ranking por `TOTAL ENGAJAMENTO` (já calculável) vs. ranking por `nsm`, com o governador selecionado destacado nos dois; se a posição no ranking mudar, uma frase automática tipo "Este governador sobe/desce N posições ao considerar qualidade em vez de volume". Fica logo depois do bloco de comparação com pares (linha ~142).
3. **Nova seção "Crescimento (CMGR)"**: dentro ou logo após o fragment `render_performance_trend` (que já lê `governor_engagement_history` com auto-refresh) — adicionar `st.metric("CMGR", ...)` com um `st.caption` fixo avisando que é **ilustrativo** enquanto o histórico acumulado for curto (mesma cautela que a Ficha 6 pede — não esconder a limitação). Reaproveita `load_engagement_history()`, já importado nesta página.

**Não muda:** matriz de quadrantes e lacuna de execução ficam como estão — não têm relação direta com NSM/CMGR/UGC.

---

### `pages/04_recommendations.py` — hoje: alertas determinísticos (`compute_recommendations`) sobre tendência, sentimento, cluster de pares

**Mudança:** estender `compute_recommendations` (em `src/dashboard/recommendations.py`) com 1-2 regras novas, mesma filosofia "regra determinística, sem redação por IA":
- Regra nova: se o governador tem tópicos no top-N de `topic_priority_score` que ele **não produziu recentemente** (comparar tópicos de `topic_priority_score` com os tópicos já cobertos no próprio discurso via `governor_discourse_topics`), gerar alerta "Tema de alta prioridade ainda não abordado: {tópico}".
- Regra opcional (se o experimento de UGC já tiver decidido a fonte): variação de volume de UGC período a período (queda acentuada = alerta).

**Não muda:** estrutura da página (seletor individual obrigatório, sem visão agregada) e as regras já existentes.

---

## Aba nova: `pages/05_funil.py` (não `04_funil.py`)

**Decisão técnica que tomei sem precisar perguntar:** manter a numeração atual (`01`-`04` intactos) e adicionar a aba de funil como `05_funil.py`, em vez de inserir como `04` e renumerar `04_recommendations.py→05`. Motivo: renumerar um arquivo existente quebra qualquer link direto (`st.page_link("pages/04_recommendations.py", ...)` no `app.py`, possíveis bookmarks/testes) sem nenhum ganho — a ordem de navegação no menu lateral do Streamlit já segue a ordem alfabética dos arquivos, então `05` aparece depois de `04` de qualquer forma. Renomear só faz sentido se a posição no menu for uma prioridade de produto explícita; não é o caso aqui.

**Conteúdo** (já decidido antes desta especificação, incluído aqui só para registro de onde entra):
- Página pura de apresentação — zero recálculo, só leitura via `DeltaRepository`.
- Uma seção por estágio RACE (Reach/Act/Convert/Engage), cada uma mostrando: nome do estágio, nível COBRA correspondente, e a métrica already-computed (`views`/PC1 para Reach, curtidas+cluster Padrão para Act/Consumir, comentários+sentimento positivo para Convert/Contribuir, **volume de UGC** para Engage/Criar — pendente da fonte de dado final do experimento de actors).
- Segue o mesmo padrão de degradação graciosa de `02_insights.py`: qualquer tabela Gold ausente vira instrução (`st.info`), não erro.
- Adicionar ao nav da Home (`app.py`, bloco `nav1-nav4` → passa a ter uma 5ª coluna ou uma segunda linha de `st.page_link`).

---

## Interatividade

| Feature | Novo? | Nota |
|---|---|---|
| Seletor global de governador | Não | Já existe (`GLOBAL_GOVERNOR_SELECTOR_KEY`), todas as seções novas o reaproveitam |
| Filtro de cluster de perfil | Não | Já existe em `render_group_filters`, só ganha dado quando Ficha 1 rodar |
| Toggle Reels/Feed em "Padrões de conteúdo" | Sim | `st.tabs` ou `st.radio` simples, só em `02_insights.py` |
| Drill-down tópico → posts que o compõem | Não recomendado nesta rodada | Aumenta escopo sem pedido explícito; registrar como ideia futura, não construir agora |

---

## Fontes de dado e responsáveis (por estágio do pipeline, não por pessoa — projeto sem times separados)

Todas as tabelas novas citadas na tabela de Métricas acima já têm dono de estágio definido no plano de implementação (Fichas 1-7): extração (UGC), modelagem (clusters de feed, tópicos de discurso), pós-modelagem/Fase 2 (perfil, NSM, ICE, CMGR). Este documento não redefine isso — só consome.

---

## Critérios de aceite

- [ ] Cada seção nova degrada graciosamente (```st.info```/```st.warning```, nunca exceção) quando sua tabela Gold ainda não existe — mesmo padrão de todas as seções atuais.
- [ ] Nenhuma página recalcula métrica que pertence ao pipeline (proibido, por exemplo, calcular NSM dentro de `03_performance.py` — só ler `governor_nsm` pronta).
- [ ] `pages/05_funil.py` não introduz nenhum cálculo próprio — só leitura + rotulagem RACE/COBRA.
- [ ] Contraste NSM vs. engajamento bruto (`03_performance.py`) mostra pelo menos 1 caso real onde o ranking muda de ordem, validando que a métrica tem valor (mesmo critério que a Ficha 5 já propõe para o Cap. 6).
- [ ] Teste automatizado por seção nova, seguindo o padrão de testes já existente do dashboard (se houver — confirmar convenção em `tests/` antes de implementar).

---

*Baseado no processo de `dashboard-specification`. Insumo direto para a ADR grande que cobre pipeline (Fichas 1-7) + dashboard (este documento) juntos.*
