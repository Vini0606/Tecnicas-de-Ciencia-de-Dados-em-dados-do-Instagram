---
status: accepted
---

# Alinhamento do código ao TCC pós-PR#84: funil COBRA-RACE, NSM, Score ICE, CMGR, tópicos de discurso oficial e reformulação do dashboard como ferramenta de growth

## Contexto

O PR [#84](https://github.com/Vini0606/Tecnicas-de-Ciencia-de-Dados-em-dados-do-Instagram/pull/84)
reescreveu Introdução/Objetivos/Referencial Teórico do TCC e inseriu blocos-roteiro (comentários
LaTeX, ainda não prosa) no Cap. 5 e Cap. 6, reorganizando a tese em torno de um **funil de
engajamento COBRA-RACE** — COBRAs (Consumers' Online Brand-Related Activities, Muntinga 2011)
mapeados num funil de growth marketing RACE (Feroz 2024), citações já presentes no `.bib`
(`MUNTINGA2011`, `FEROZ2024`). Um gap analysis desta sessão (leitura completa de Cap. 5/6/7 +
cruzamento com o código) confirmou que **nada no pipeline hoje computa ou expõe uma visão em
estágios de funil**, e apontou lacunas concretas: nenhuma clusterização de posts do feed (só
reels), nenhuma extração de transcrição de vídeo, nenhum modelo de tópicos separado para o
"discurso oficial" (BERTopic hoje roda só sobre comentários e sobre captions-como-preditor, ADR
0019), e nenhuma métrica de volume de UGC (conteúdo gerado por terceiros).

Três documentos do usuário, externos ao repositório (`Plano_Implementacao_Analises.docx`,
`Adendo_Plano_Implementacao.docx` e `Ficha8_Coleta_UGC.docx`, todos em Downloads), chegaram já com
um plano técnico detalhado por "ficha" (arquivo a tocar, tabela Gold, teste, ordem de dependência)
para fechar essas lacunas. Verificação de código nesta sessão confirmou que esses documentos são
mais precisos que o gap analysis inicial: existe uma "Fase 2" já esboçada
(`scripts/run_profile_clustering_engagement.py` + `lambdas/model/handler.py`, que já chama
`cluster_governor_profiles` e grava em `governor_profile_clusters_engagement`) — construída, mas
**não conectada** a `lambdas/orchestrator/`. Uma pesquisa de actors do Apify Store (`/research`,
`docs/research/apify-instagram-actors-cobra-mapping.md`, commit `3c90476`) encontrou ainda que o
`apify/instagram-reel-scraper` (já integrado em `src/data_extract/scraper.py`) tem uma flag paga
`includeTranscript` — ou seja, extrair transcrição não exige um pipeline de ASR do zero, só
habilitar uma opção no actor já em uso, no mesmo padrão de `includeSharesCount` (também não
habilitada hoje). Essa mesma pesquisa mapeou, para o nível "Creating" do COBRA (volume de UGC),
duas rotas técnicas viáveis: reconfigurar o actor de perfil já integrado (`shu8hvrXbJbY3Eb9W` =
`apify/instagram-scraper` genérico) com `resultsType: "mentions"`, ou adicionar
`apify/instagram-tagged-scraper` (oficial, schema de output confirmado, $1,50/1000). O terceiro
documento (`Ficha8_Coleta_UGC.docx`) avaliou um actor de terceiros que o usuário havia cogitado
(`fetch_cat/instagram-mentions-scraper`) e recomendou rejeitá-lo por risco de reprodutibilidade
("under maintenance", 2 usuários, 0 avaliações) — reforçando a preferência por um actor consolidado
já mapeado na pesquisa — e propôs tratar UGC não como troca de actor, mas como uma frente de coleta
Medallion própria (Ficha 8).

As decisões abaixo saíram de uma rodada de `/grilling` cruzando os dois documentos do usuário com
essas descobertas de código, e uma especificação de dashboard (`/dashboard-specification`,
`docs/dashboard/especificacao-reformulacao-growth.md`) que resolveu, página a página, onde cada
métrica nova entra no esqueleto já existente (ADR [0017](0017-reestruturacao-do-dashboard-para-produto-externo.md)).
Esta ADR segue o mesmo padrão de escopo grande e múltiplas fichas sequenciais da ADR
[0019](0019-regressao-de-performance-por-post-video-e-estatico-com-lasso-e-bertopic.md) — inclusive
na decisão de registrar tudo numa ADR só antes de abrir issues, em vez de fragmentar o registro.

## Decisão

### Frente 1 — Pipeline/Modelagem (7 fichas, ordem de execução por dependência)

1. **Clusterização de Perfis** — ativar o que já existe esboçado: conectar
   `lambdas/model/handler.py` a `lambdas/orchestrator/`, validar a saída de
   `governor_profile_clusters_engagement` e adicionar teste análogo a `test_model_enricher.py`.
   Não é trabalho do zero.
2. **Clusterização de Posts do Feed** — nova, reaproveitando ~90% do pipeline PCA→AutoClusterHPO de
   `cluster_reels`. Grava em `governor_clusters` (existente) com uma **coluna discriminadora
   `content_type`** (`reel`/`feed`), não uma tabela nova — mesma granularidade conceitual (post),
   mesma pipeline, features de entrada diferentes (feed não tem `videoPlayCount`/`videoDuration`,
   logo PCA com cargas diferentes — já esperado, mesmo numa tabela só).
3. **Sentimento de Legendas e Transcrições** — estender `ModelEnricher` para a fonte "legenda"
   (dado já existe em `caption`). Habilitar `includeTranscript` no `apify/instagram-reel-scraper`
   para transcrições (decisão revertida nesta sessão: inicialmente adiada para uma fase futura por
   ser tratada como "construir ASR do zero"; revertida ao descobrir que é uma flag paga por minuto
   no actor já integrado). `governor_sentiment` ganha uma coluna de fonte
   (`comentario`/`legenda`/`transcricao`). Ponto de atenção: o modelo de sentimento
   (`cardiffnlp/...`) foi treinado em tweets — validar seu comportamento em legenda/transcrição
   formal de assessoria, ou documentar como limitação explícita no Cap. 7.
4. **Tópicos de Legendas+Transcrições ("Discurso Oficial")** — BERTopic sobre um corpus novo
   (legendas+transcrições), reaproveitando o mesmo pipeline de tópicos já usado em comentários.
   Grava em **tabela nova `governor_discourse_topics`**, não estende `governor_sentiment` — as duas
   fontes (fala da assessoria vs. reação do público) são granularidades conceitualmente distintas, e
   o Cap. 5/6 do TCC as trata como um contraste entre duas fontes, não uma mistura. Volume esperado
   baixo (~810 legendas) deve gerar menos de 50 tópicos estáveis — não forçar o mesmo número usado
   para comentários.
5. **North Star Metric** — `NSM = (comentários positivos / comentários totais) ponderado pelo
   alcance médio`, por perfil. Vive em um **estágio pós-modelagem** (não no `EngagementAggregator`
   original), porque depende de `governor_sentiment` **e** `governor_engagement` já calculados
   juntos. Tabela nova `governor_nsm`. Entrega esperada no Cap. 6: contrastar ranking por NSM vs.
   ranking por engajamento bruto, mostrando que a ordem muda.
6. **Score ICE (Priorização de Tópicos)** — `Score = Impacto × Confiança × Facilidade`; Impacto =
   alcance do tópico × proporção de sentimento positivo; Confiança = confiança média do
   classificador de sentimento no tópico; Facilidade = heurística ou fixa em 1 na v1 (decisão
   documentada, não um número inventado sem justificativa). 100% automatizado — nenhum input humano
   do assessor é necessário para calcular o score. Tabela nova `topic_priority_score`, uma linha por
   tópico, rodando pós-modelagem junto da NSM (mesma dependência de `governor_sentiment` já
   refinado via Gemini).
7. **CMGR e Retenção** — módulo novo que lê `governor_engagement_history`/
   `governor_sentiment_history` (já existem, append) e calcula o crescimento mensal composto.
   Calculado por último no pipeline, mas a coleta que o alimenta deve começar cedo. O resultado é
   **ilustrativo, não conclusivo**, enquanto poucas execuções tiverem se acumulado — isso deve ser
   declarado como limitação explícita no Cap. 6/7, não escondido.

Ordem de execução: 1 → 2 → 3 → 4 → (5 e 6, mesma dependência, podem ser paralelas) → 7 (calculado
por último; coleta para ele deve rodar desde o início) → Ficha 8/UGC (depois de 1-7 fechadas, não
compete pelos mesmos dados).

### Ficha 8 — Pipeline de Coleta de UGC de Criação ("Creating" do COBRA)

Ao contrário das 7 fichas acima, UGC não é extensão do pipeline existente — é uma **frente de coleta
nova**, com Medallion completo (Bronze→Silver→Gold), incluída nesta rodada e executada **depois das
Fichas 1-7** (não compete com as análises que já podem rodar sobre dado existente).

**Decisão de actor**: rejeitar `fetch_cat/instagram-mentions-scraper` como dependência, apesar de
ter os campos certos (`caption`, `matchTypes`, engajamento, `isAd`/`isPaidPartnership`) — está
"under maintenance", com 2 usuários e 0 avaliações, risco de descontinuação inaceitável para
reprodutibilidade acadêmica (se o actor sair do ar, o dado não se reproduz e o TCC perde
rastreabilidade). Preferir um actor consolidado de tagged/mentions: `apify/instagram-tagged-scraper`
(oficial, 9.999 usuários, 5.0★, $1,50/1000, schema de output confirmado — já mapeado em
`docs/research/apify-instagram-actors-cobra-mapping.md`) é o candidato. Antes de comprometer o
pipeline: rodar um **piloto pequeno** (`resultsLimit` baixo) nos 27 perfis, medir volume real e
estabilidade, e confirmar os nomes exatos de campo na aba Output do actor antes de fixar o schema
Delta. A reconfiguração do actor de perfil já integrado (`resultsType: "mentions"`) fica registrada
como alternativa secundária a considerar no piloto, não como uma segunda rota em produção — ver
Opções consideradas.

**Campos a coletar** (mapeados ao schema do projeto): `caption` (sentimento/tópicos do UGC);
`matchTypes` (distingue marcação visual de menção textual); `likesCount`/`commentsCount`/
`videoPlayCount` (engajamento do próprio UGC); `authorUsername`/`authorIsVerified` (perfil de quem
criou); `isPaidPartnership`/`isAd`/`isAffiliate` (crítico — separa UGC orgânico de publi paga antes
de agregar); `timestamp` (série temporal, dialoga com CMGR).

**Arquivos a tocar** (mesmo padrão Medallion do resto do projeto): `src/data_extract/scraper.py`
(nova função de coleta do actor de mentions, landing zone própria por `run_id`);
`src/schemas_delta.py` (contrato Bronze/Silver/Gold da nova tabela, `nullable` onde a fonte pode
faltar); `src/features/silver/` (novo cleaner de UGC — dedup por `id`/`shortCode`, normalização de
handles); `src/features/gold/` (agregação por governador: contagem, engajamento médio, % orgânico
vs. pago); nova tabela Gold `governor_ugc_mentions` (uma linha por post de UGC); `tests/` (cleaner e
agregador, padrão dos testes existentes).

**Pontos de atenção**:
- Separar orgânico de pago **antes** de agregar — contar publi (`isPaidPartnership`/`isAd`) como
  "apoio espontâneo" infla falsamente o nível de criação.
- Viés de volume: governadores mais populares terão muito mais menções — declarar esse viés ou
  normalizar por tamanho de audiência, não comparar contagem bruta entre perfis sem ressalva.
- Mesma ressalva do `cardiffnlp/...` (treinado em tweets) já registrada para legendas/transcrições
  (Ficha 3) se aplica a UGC — texto de terceiros é um registro diferente do que o modelo foi
  treinado para classificar.
- Privacidade/ética: são posts de cidadãos comuns, não de figuras públicas — coletar só dado
  público, anonimizar autores em análises agregadas, e registrar a conformidade explicitamente (a
  banca vai perguntar).

Métrica resultante para o funil: `COUNT` de posts de terceiros marcando/mencionando o perfil no
período, mais `SUM(likesCount + commentsCount)` desses posts = volume/engajamento de UGC.

### Frente 2 — Funil RACE↔COBRA + Dashboard

O funil é uma **camada de apresentação**, não um estágio de pipeline: não calcula nenhum número
novo, só rotula e organiza o que as fichas 1-7 (+ UGC) já produzem. Mapeamento adotado:

| Estágio (RACE) | Nível COBRA | Métrica |
|---|---|---|
| Reach | — | views / alcance (PC1) |
| Act | Consumir | curtidas; cluster "Padrão" |
| Convert | Contribuir | comentários + sentimento positivo |
| Engage | Criar | volume/engajamento de UGC |

A linha "Engage/Criar" é uma **revisão deliberada** do roteiro original do Cap. 6 do TCC, que usava
"comentários em debate (cluster Viral)" — uma métrica de reação do público, semanticamente mais
próxima de "Contribuir" que de "Criar". A substituição por volume de UGC só vira número real quando
a Ficha 8 (seção anterior) entregar `governor_ugc_mentions`, o que por sua vez depende do piloto de
validação do `apify/instagram-tagged-scraper` confirmar volume/estabilidade suficientes; até lá, o
estágio "Engage" no texto e no dashboard permanece com essa métrica pendente, não com a métrica
antiga do roteiro.

Dois destinos, ambos obrigatórios (não um obrigatório e um opcional, como um rascunho anterior do
adendo sugeria — decisão do usuário nesta sessão foi mexer também nas páginas existentes, não só
adicionar uma aba isolada):

1. **Texto do TCC** — seção "Do Diagnóstico à Ação" do Cap. 6 (roteiro já existe no `.tex`),
   citações `FEROZ2024` (RACE) e `MUNTINGA2011` (COBRA) já presentes no `.bib`. Sem código.
2. **Dashboard** — especificação completa em `docs/dashboard/especificacao-reformulacao-growth.md`.
   Resumo:
   - Aba nova `pages/05_funil.py` (não `04_funil.py` — evita renumerar `04_recommendations.py` sem
     ganho, já que o menu do Streamlit ordena por nome de arquivo de qualquer forma). Zero
     recálculo — só leitura via `DeltaRepository`, uma seção por estágio RACE.
   - **Home**: ganha 1 métrica de NSM médio no KPI row.
   - **`01_explorar.py`**: liga a coluna de cluster de perfil (já importada, não usada) como cor no
     scatter; NSM/volume-UGC entram automaticamente nas colunas numéricas via enrich já existente.
   - **`02_insights.py`** (mais afetada): duas seções novas — "Discurso vs. Reação" (tópicos de
     `governor_discourse_topics` lado a lado com os tópicos de comentário já calculados) e
     "Prioridade de Temas / Score ICE" (tabela de `topic_priority_score`); "Padrões de conteúdo dos
     reels" passa a agrupar também por `content_type` (Reels e Feed).
   - **`03_performance.py`**: `nsm` entra em `METRICAS_COMPARACAO`; nova seção "Bruto vs.
     Qualificado" contrastando ranking por engajamento cru vs. NSM; CMGR no fragment de tendência já
     existente, com aviso explícito de "ilustrativo".
   - **`04_recommendations.py`**: nova regra determinística — tema de alta prioridade (Score ICE)
     ainda não abordado no discurso do próprio governador.
   - Achado relevante: `02_insights.py` e `src/dashboard/filters.py` **já têm código pronto e
     degradado** esperando por `governor_profile_clusters_engagement` — a Ficha 1 sozinha já
     alimenta essa parte do dashboard, sem nenhum código novo de UI.

## Por que

- Fichas 1-7 seguem a ordem de dependência real dos dados (perfil e feed são independentes entre
  si; sentimento de legenda/transcrição precisa existir antes dos tópicos de discurso; NSM e ICE
  dependem do sentimento já refinado; CMGR depende de histórico acumulado) — a ordem não é
  arbitrária, é a que os dois documentos do usuário e a verificação de código confirmaram como
  viável.
- NSM e ICE vivem em um estágio pós-modelagem separado (a "Fase 2" que o código já esboça, não o
  `EngagementAggregator` original) porque ambos dependem de sentimento e engajamento já calculados
  juntos — calcular antes inverteria a ordem do pipeline e forçaria recomputação.
- Tabela separada para tópicos de discurso (`governor_discourse_topics`) em vez de estender
  `governor_sentiment`: as duas fontes têm papéis conceituais opostos no contraste que o TCC propõe
  (fala da assessoria vs. reação do público); misturar tudo numa tabela indexada por comentário
  forçaria uma granularidade mista ou um join estranho.
- Transcrição de vídeo entra nesta rodada (decisão revertida) porque o custo real é uma flag paga
  por minuto num actor já integrado, não um pipeline de ASR construído do zero — a avaliação inicial
  de custo/complexidade que motivou adiar essa peça estava desatualizada assim que a pesquisa de
  actors trouxe esse dado.
- UGC vira pipeline completo (Ficha 8) em vez de trabalho futuro porque o usuário decidiu assumir o
  escopo maior mesmo com o projeto já ambicioso (3 fontes textuais, clustering em 3 níveis, funil,
  NSM, ICE) — mas com uma salvaguarda: um piloto pequeno antes de comprometer o schema Delta, porque
  o actor recomendado (`apify/instagram-tagged-scraper`) tem schema confirmado por exemplo, mas
  nenhum teste real nos 27 perfis do projeto ainda foi rodado.
- `fetch_cat/instagram-mentions-scraper` foi descartado apesar de ter os campos mais completos
  (`matchTypes`, `isAd`/`isPaidPartnership`) porque reprodutibilidade acadêmica pesa mais que
  completude de schema — um actor "under maintenance" com 2 usuários pode simplesmente desaparecer
  antes da defesa do TCC, e o dado deixaria de ser reproduzível.
- "Engage/Criar" muda de "comentários em debate" para "volume de UGC" porque comentário — mesmo em
  debate — continua sendo uma atividade de reação de quem já está na publicação do governador, não
  de criação de conteúdo novo por um terceiro; UGC é a métrica que bate literalmente com a definição
  de "Creating" do framework COBRA que o TCC cita.
- Dashboard obrigatório nas duas frentes (aba nova + páginas existentes), não só a aba opcional,
  porque o pedido original do usuário foi por uma "reformulação completa como ferramenta de growth"
  — uma aba isolada sem tocar as páginas que a assessoria já usa no dia a dia não cumpriria isso.
- Registrar tudo numa ADR grande, com issues só depois das duas frentes fechadas: decisão explícita
  do usuário nesta sessão, mesmo padrão de "escopo completo antes de fragmentar" já visto nas
  rodadas de grilling anteriores do projeto (ADR 0019).

## Opções consideradas

- **Adiar transcrição para uma fase futura** (decisão inicial desta sessão) — revertida assim que a
  pesquisa de actors mostrou que o custo é uma flag paga, não um pipeline de ASR novo.
- **Estender `governor_sentiment` com os tópicos de discurso** em vez de criar
  `governor_discourse_topics` — rejeitada: mistura de granularidade conceitual entre fala da
  assessoria e reação do público.
- **Tabela Gold nova para clusters de feed** (`governor_feed_clusters`) em vez de coluna
  discriminadora em `governor_clusters` — rejeitada: mesma pipeline conceitual, uma tabela só
  simplifica consumo no dashboard (uma query, filtro por `content_type`, em vez de duas tabelas a
  unir).
- **Score ICE com input humano do assessor** para a componente Facilidade — rejeitada nesta rodada;
  v1 usa heurística ou valor fixo, documentado como limitação, mantendo o score 100% automatizado.
- **Manter "comentários em debate" como métrica de Engage/Criar**, como o roteiro original do Cap. 6
  e o adendo do usuário traziam — rejeitada nesta sessão em favor de volume de UGC, por
  inconsistência semântica com o nível "Criar" do COBRA.
- **Dashboard só com a aba nova de funil, sem mexer nas páginas existentes** (opção que o adendo do
  usuário apresentava como suficiente) — rejeitada pelo usuário; escolheu também reformular as
  páginas existentes.
- **Rodar dois actors de UGC em paralelo em produção para comparar** (decisão inicial desta sessão)
  — substituída por uma rota única (`apify/instagram-tagged-scraper`) validada por piloto pequeno
  antes de comprometer o pipeline, depois que a Ficha 8 trouxe critério de reprodutibilidade que
  desempatava a favor de um actor consolidado.
- **Adotar `fetch_cat/instagram-mentions-scraper`** (actor que o usuário havia cogitado, com campos
  mais completos) — rejeitada por risco de descontinuação incompatível com reprodutibilidade
  acadêmica.
- **Tratar UGC como Trabalho Futuro no Cap. 7**, em vez de pipeline completo nesta rodada (opção que
  a própria Ficha 8 recomendava, dado o escopo já grande do projeto) — rejeitada pelo usuário, que
  escolheu assumir o escopo maior.
- **Abrir ADRs/issues separadas por ficha**, conforme iam sendo fechadas — rejeitada pelo usuário;
  escolheu uma ADR grande cobrindo tudo, com issues só depois de ambas as frentes fechadas.

## Consequências

- **Nada foi implementado nesta sessão** — esta ADR registra escopo e desenho; a implementação
  (lambda de perfil conectada ao orquestrador, clustering de feed, extensão do `ModelEnricher`,
  `includeTranscript` habilitado, BERTopic de discurso, NSM, Score ICE, CMGR, o pipeline Medallion
  de UGC da Ficha 8, a página de funil e as mudanças nas 4 páginas existentes) fica para issues
  futuras, seguindo o padrão já validado do projeto (issue no GitHub rotulada `ready-for-agent` →
  TDD → `/code-review` Standards+Spec → commit), com `/wayfinder` recomendado dado o tamanho (maior
  que a ADR 0019).
- O piloto de validação do actor de UGC (`apify/instagram-tagged-scraper`) bloqueia a métrica final
  de "Engage/Criar" no funil (texto do Cap. 6 e `pages/05_funil.py`) — até ele confirmar volume e
  estabilidade suficientes nos 27 perfis, essa métrica não tem fonte de dado definitiva. Se o piloto
  falhar, a Ficha 8 precisa de uma segunda rota (ex.: reconfigurar `resultsType: "mentions"` no actor
  de perfil já integrado) antes de a Ficha 8 poder ser dada como fechada.
- `governor_sentiment` ganha uma coluna de fonte (`comentario`/`legenda`/`transcricao`) —
  qualquer consumidor existente que já lê essa tabela sem filtrar por fonte passa a misturar as três
  granularidades nas agregações, a menos que seja atualizado para filtrar.
- `governor_clusters` ganha `content_type` — consumidores existentes que já leem essa tabela sem
  filtrar por tipo passam a ver reels e posts de feed juntos.
- O custo de extração cresce: `includeTranscript` (cobrado por minuto de vídeo) e mais um actor
  Apify (`apify/instagram-tagged-scraper`, pendente de confirmação pelo piloto) rodando por
  governador monitorado — impacto de custo recorrente, não pontual.
- A Ficha 8 introduz uma frente de coleta sobre dados de **terceiros** (cidadãos comuns, não figuras
  públicas) — exige tratamento de privacidade/anonimização em análises agregadas e filtragem
  explícita de conteúdo pago (`isPaidPartnership`/`isAd`) antes de qualquer agregação, sob risco de
  inflar artificialmente o nível "Criar" do funil com publi contabilizada como apoio espontâneo.
- CMGR entra no dashboard como métrica declaradamente ilustrativa enquanto o histórico for curto —
  qualquer leitura precisa comunicar essa limitação; não é um gap temporário que desaparece sozinho,
  depende de tempo de operação acumulado.
- Três fontes externas ao repositório (`Plano_Implementacao_Analises.docx`,
  `Adendo_Plano_Implementacao.docx`, `Ficha8_Coleta_UGC.docx`, Downloads do usuário) fundamentam
  parte desta decisão e não estão versionadas no projeto — se o usuário quiser rastreabilidade
  completa, vale considerar anexá-los a `docs/` em uma revisão futura.
