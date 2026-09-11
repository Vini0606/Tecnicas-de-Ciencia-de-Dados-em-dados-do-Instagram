"""
Schemas PyArrow para as camadas Bronze, Silver e Gold (Delta Lake).
Gerados para validação de contrato de dados na arquitetura Medallion.
"""

import pyarrow as pa

# BRONZE
BRONZE_PROFILES_SCHEMA = pa.schema(
    [
        pa.field("id", pa.string(), nullable=True),
        pa.field("username", pa.string(), nullable=True),
        pa.field("fullName", pa.string(), nullable=True),
        pa.field("businessCategoryName", pa.string(), nullable=True),
        pa.field("inputUrl", pa.string(), nullable=True),
        pa.field("followersCount", pa.int64(), nullable=True),
        pa.field("followsCount", pa.int64(), nullable=True),
        pa.field("postsCount", pa.int64(), nullable=True),
        pa.field("igtvVideoCount", pa.int64(), nullable=True),
        pa.field("verified", pa.bool_(), nullable=True),
        pa.field("private", pa.bool_(), nullable=True),
        pa.field("isBusinessAccount", pa.bool_(), nullable=True),
        pa.field("hasChannel", pa.bool_(), nullable=True),
        pa.field("joinedRecently", pa.bool_(), nullable=True),
        pa.field("_ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("_run_id", pa.string(), nullable=False),
        pa.field("_source", pa.string(), nullable=False),
    ]
)

BRONZE_POSTS_SCHEMA = pa.schema(
    [
        pa.field("id", pa.string(), nullable=True),
        pa.field("ownerId", pa.string(), nullable=True),
        pa.field("ownerUsername", pa.string(), nullable=True),
        pa.field("inputUrl", pa.string(), nullable=True),
        pa.field("commentsCount", pa.int64(), nullable=True),
        pa.field("likesCount", pa.int64(), nullable=True),
        pa.field("timestamp", pa.string(), nullable=True),
        pa.field("type", pa.string(), nullable=True),
        pa.field("shortCode", pa.string(), nullable=True),
        pa.field("caption", pa.string(), nullable=True),
        pa.field("videoViewCount", pa.int64(), nullable=True),
        pa.field("videoPlayCount", pa.int64(), nullable=True),
        pa.field("videoDuration", pa.float64(), nullable=True),
        pa.field("locationName", pa.string(), nullable=True),
        pa.field("_ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("_run_id", pa.string(), nullable=False),
        pa.field("_source", pa.string(), nullable=False),
    ]
)

BRONZE_REELS_SCHEMA = pa.schema(
    [
        pa.field("id", pa.string(), nullable=True),
        pa.field("ownerId", pa.string(), nullable=True),
        pa.field("ownerUsername", pa.string(), nullable=True),
        pa.field("inputUrl", pa.string(), nullable=True),
        pa.field("commentsCount", pa.int64(), nullable=True),
        pa.field("likesCount", pa.int64(), nullable=True),
        pa.field("videoViewCount", pa.int64(), nullable=True),
        pa.field("videoPlayCount", pa.int64(), nullable=True),
        pa.field("videoDuration", pa.float64(), nullable=True),
        pa.field("timestamp", pa.string(), nullable=True),
        pa.field("type", pa.string(), nullable=True),
        pa.field("shortCode", pa.string(), nullable=True),
        pa.field("isSponsored", pa.bool_(), nullable=True),
        pa.field("isCommentsDisabled", pa.bool_(), nullable=True),
        pa.field("isPinned", pa.bool_(), nullable=True),
        pa.field("latestComments", pa.string(), nullable=True),
        # ADR 0020 (Ficha 3) / issue #88: transcrição de fala do reel, via
        # flag paga `includeTranscript` do `apify/instagram-reel-scraper`
        # (ver `ScraperConfig.include_transcript`). Nullable -- nem todo
        # reel tem fala (vídeo mudo, música só) ou a flag pode estar
        # desligada na execução (custo por minuto de vídeo).
        pa.field("transcript", pa.string(), nullable=True),
        pa.field("_ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("_run_id", pa.string(), nullable=False),
        pa.field("_source", pa.string(), nullable=False),
    ]
)

# ADR 0020 (Ficha 8) / issue #93: UGC de criação -- posts de TERCEIROS que
# marcam/mencionam o perfil do governador (nível "Creating" do COBRA),
# via `apify/instagram-tagged-scraper` (ScraperConfig.mentions_actor_id).
# Quase todo campo abaixo é `nullable=True` de propósito: o piloto pequeno
# exigido pela issue (`scripts/run_apify_mentions_pilot.py`) ainda NÃO foi
# executado contra os 27 perfis reais nesta sessão (sem APIFY_API_TOKEN no
# ambiente do agente, e a chamada real gera custo na conta Apify) -- os
# nomes de campo abaixo seguem a especificação da issue/ADR, cruzada com
# `docs/research/apify-instagram-actors-cobra-mapping.md` §7.1, mas não
# foram confirmados 1:1 contra um exemplo de output real do actor escolhido
# para estes perfis. `authorUsername`/`ownerUsername` ficam como campos
# brutos candidatos lado a lado (o cleaner normaliza os dois num só) porque
# a doc de pesquisa confirma em prosa que existe um campo de autor do post,
# mas não confirma o nome exato -- mesma incerteza para `matchTypes`
# (tagged vs. mentioned, ver §7.1 "Limitação declarada").
BRONZE_UGC_MENTIONS_SCHEMA = pa.schema(
    [
        pa.field("id", pa.string(), nullable=True),
        pa.field("shortCode", pa.string(), nullable=True),
        pa.field("type", pa.string(), nullable=True),
        pa.field("caption", pa.string(), nullable=True),
        # Lista de usernames marcados/mencionados no post (serializada como
        # JSON string pelo `BronzeWriter._add_ingestion_metadata`, mesmo
        # tratamento de qualquer campo list/dict) -- é o único campo com
        # exemplo real confirmado na pesquisa (`"mentions": ["zelenskiy_..."]`),
        # e por isso a base usada para correlacionar cada post ao governador
        # marcado (`SILVER_UGC_MENTIONS_SCHEMA.governor_username`).
        pa.field("mentions", pa.string(), nullable=True),
        # Distingue marcação visual ("tagged") de menção textual ("mentioned")
        # -- campo do actor rejeitado (`fetch_cat/...`) que o piloto precisa
        # confirmar se o actor escolhido também expõe.
        pa.field("matchTypes", pa.string(), nullable=True),
        pa.field("likesCount", pa.int64(), nullable=True),
        pa.field("commentsCount", pa.int64(), nullable=True),
        pa.field("videoPlayCount", pa.int64(), nullable=True),
        pa.field("timestamp", pa.string(), nullable=True),
        pa.field("authorUsername", pa.string(), nullable=True),
        pa.field("ownerUsername", pa.string(), nullable=True),
        pa.field("authorIsVerified", pa.bool_(), nullable=True),
        # Crítico (ADR 0020, Ficha 8): separa UGC orgânico de publi paga --
        # sem isso, `GovernorUGCAggregator` contaria publi como "apoio
        # espontâneo" e infla falsamente o nível "Criar" do COBRA.
        pa.field("isPaidPartnership", pa.bool_(), nullable=True),
        pa.field("isAd", pa.bool_(), nullable=True),
        pa.field("isAffiliate", pa.bool_(), nullable=True),
        pa.field("_ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("_run_id", pa.string(), nullable=False),
        pa.field("_source", pa.string(), nullable=False),
    ]
)

# SILVER
SILVER_PROFILES_SCHEMA = pa.schema(
    [
        pa.field("id", pa.string(), nullable=False),
        pa.field("username", pa.string(), nullable=False),
        pa.field("fullName", pa.string(), nullable=True),
        pa.field("inputUrl", pa.string(), nullable=True),
        pa.field("followersCount", pa.int32(), nullable=False),
        pa.field("followsCount", pa.int32(), nullable=False),
        pa.field("postsCount", pa.int32(), nullable=False),
        pa.field("verified", pa.bool_(), nullable=False),
        pa.field("private", pa.bool_(), nullable=False),
        pa.field("isBusinessAccount", pa.bool_(), nullable=False),
        pa.field("businessCategoryName", pa.string(), nullable=True),
        pa.field("_ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("_run_id", pa.string(), nullable=False),
        pa.field("_source_layer", pa.string(), nullable=False),
    ]
)

SILVER_POSTS_SCHEMA = pa.schema(
    [
        pa.field("id", pa.string(), nullable=False),
        pa.field("ownerId", pa.string(), nullable=False),
        pa.field("ownerUsername", pa.string(), nullable=False),
        pa.field("inputUrl", pa.string(), nullable=True),
        pa.field("commentsCount", pa.int64(), nullable=False),
        pa.field("likesCount", pa.int64(), nullable=False),
        pa.field("data_hora", pa.timestamp("us"), nullable=False),
        pa.field("Tipo", pa.string(), nullable=False),
        # Campo bruto do Apify (Image/Video/Sidecar), preservado à parte de
        # `Tipo` (FEED/REELS) -- ADR 0019 (parte A): preditor de Formato da
        # regressão de performance-por-post.
        pa.field("type_raw", pa.string(), nullable=True),
        pa.field("shortCode", pa.string(), nullable=True),
        pa.field("caption", pa.string(), nullable=True),
        # ADR 0019 (parte A): dado já coletado no Bronze, antes descartado em
        # POSTS_COLUMNS_TO_DROP -- alimenta o BERTopic de tema sobre captions
        # (parte B).
        pa.field("hashtags", pa.string(), nullable=True),
        pa.field("videoPlayCount", pa.int64(), nullable=True),
        pa.field("videoDuration", pa.float64(), nullable=True),
        pa.field("_ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("_run_id", pa.string(), nullable=False),
        pa.field("_source_layer", pa.string(), nullable=False),
    ]
)

SILVER_REELS_SCHEMA = pa.schema(
    [
        pa.field("id", pa.string(), nullable=False),
        pa.field("ownerId", pa.string(), nullable=False),
        pa.field("ownerUsername", pa.string(), nullable=False),
        pa.field("inputUrl", pa.string(), nullable=True),
        pa.field("commentsCount", pa.int64(), nullable=False),
        pa.field("likesCount", pa.int64(), nullable=False),
        pa.field("videoPlayCount", pa.int64(), nullable=True),
        pa.field("videoDuration", pa.float64(), nullable=True),
        pa.field("data_hora", pa.timestamp("us"), nullable=False),
        pa.field("Tipo", pa.string(), nullable=False),
        # Mesmo campo bruto de SILVER_POSTS_SCHEMA -- reels são inerentemente
        # vídeo hoje, mas preserva a granularidade original por consistência
        # (ADR 0019, parte A).
        pa.field("type_raw", pa.string(), nullable=True),
        pa.field("shortCode", pa.string(), nullable=True),
        pa.field("isSponsored", pa.bool_(), nullable=True),
        pa.field("isCommentsDisabled", pa.bool_(), nullable=True),
        pa.field("Total de Engajamento", pa.int64(), nullable=False),
        # ADR 0020 (Ficha 3) / issue #88: mesmo campo bruto de
        # BRONZE_REELS_SCHEMA, propagado sem transformação (`PostCleaner`
        # não faz limpeza especial de texto além do já aplicado a `caption`)
        # -- alimenta `governor_sentiment` (fonte "transcricao").
        pa.field("transcript", pa.string(), nullable=True),
        pa.field("_ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("_run_id", pa.string(), nullable=False),
        pa.field("_source_layer", pa.string(), nullable=False),
    ]
)

SILVER_COMMENTS_SCHEMA = pa.schema(
    [
        pa.field("id_reel", pa.string(), nullable=True),
        pa.field("id_comment", pa.string(), nullable=True),
        pa.field("text", pa.string(), nullable=True),
        pa.field("comprimento texto", pa.int64(), nullable=False),
        pa.field("ownerUsername", pa.string(), nullable=True),
        pa.field("likesCount", pa.int64(), nullable=True),
        pa.field("repliesCount", pa.int64(), nullable=True),
        pa.field("timestamp", pa.string(), nullable=True),
        pa.field("inputUrl", pa.string(), nullable=True),
        pa.field("_ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("_run_id", pa.string(), nullable=False),
        pa.field("_source_layer", pa.string(), nullable=False),
    ]
)

SILVER_GOVERNORS_METADATA_SCHEMA = pa.schema(
    [
        pa.field("inputUrl", pa.string(), nullable=False),
        pa.field("nome", pa.string(), nullable=False),
        pa.field("uf", pa.string(), nullable=True),
        pa.field("partido", pa.string(), nullable=True),
        pa.field("_ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("_run_id", pa.string(), nullable=False),
        pa.field("_source_layer", pa.string(), nullable=False),
    ]
)

# ADR 0020 (Ficha 8) / issue #93: `id`/`shortCode` ficam `nullable=True` (em
# vez do padrão `id` NOT NULL de SILVER_POSTS/REELS/PROFILES) porque o piloto
# do actor ainda não confirmou que `id` é sempre preenchido -- o cleaner
# descarta linhas sem `id` E sem `shortCode` (ambos ausentes = registro
# inidentificável), então a dedup continua garantida na prática.
SILVER_UGC_MENTIONS_SCHEMA = pa.schema(
    [
        pa.field("id", pa.string(), nullable=True),
        pa.field("shortCode", pa.string(), nullable=True),
        pa.field("type", pa.string(), nullable=True),
        pa.field("caption", pa.string(), nullable=True),
        pa.field("matchTypes", pa.string(), nullable=True),
        # Derivado de `mentions` (Bronze) cruzado com a lista de usernames de
        # governador informada ao cleaner -- não é um campo bruto do actor.
        # Nulo quando `mentions` não bate com nenhum username conhecido
        # (post não correlacionável a um governador do projeto).
        pa.field("governor_username", pa.string(), nullable=True),
        # Normalização de `authorUsername`/`ownerUsername` (Bronze) num só
        # campo -- "normalização de handles" pedida pela issue #93.
        pa.field("authorUsername", pa.string(), nullable=True),
        pa.field("authorIsVerified", pa.bool_(), nullable=False),
        pa.field("isPaidPartnership", pa.bool_(), nullable=False),
        pa.field("isAd", pa.bool_(), nullable=False),
        pa.field("isAffiliate", pa.bool_(), nullable=False),
        pa.field("likesCount", pa.int64(), nullable=False),
        pa.field("commentsCount", pa.int64(), nullable=False),
        pa.field("videoPlayCount", pa.int64(), nullable=True),
        pa.field("data_hora", pa.timestamp("us"), nullable=False),
        pa.field("_ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("_run_id", pa.string(), nullable=False),
        pa.field("_source_layer", pa.string(), nullable=False),
    ]
)

# GOLD
GOLD_ENGAGEMENT_SCHEMA = pa.schema(
    [
        pa.field("id", pa.string(), nullable=False),
        pa.field("username", pa.string(), nullable=False),
        pa.field("fullName", pa.string(), nullable=True),
        pa.field("inputUrl", pa.string(), nullable=True),
        pa.field("followersCount", pa.int32(), nullable=False),
        pa.field("followsCount", pa.int32(), nullable=False),
        pa.field("postsCount", pa.int32(), nullable=False),
        pa.field("TOTAL ENGAJAMENTO", pa.int64(), nullable=False),
        pa.field("% ENGAJAMENTO", pa.float64(), nullable=False),
        pa.field("_WC_COMENTARIO", pa.float64(), nullable=False),
        pa.field("RECENCIA", pa.float64(), nullable=False),
        pa.field("FREQUENCIA", pa.float64(), nullable=False),
        pa.field("commentsSum", pa.int64(), nullable=False),
        pa.field("likesSum", pa.int64(), nullable=False),
        pa.field("count", pa.int64(), nullable=False),
        pa.field("minData", pa.timestamp("us"), nullable=True),
        pa.field("maxData", pa.timestamp("us"), nullable=True),
        pa.field("_run_id", pa.string(), nullable=False),
        pa.field("_generated_at", pa.timestamp("us", tz="UTC"), nullable=False),
    ]
)

GOLD_SENTIMENT_SCHEMA = pa.schema(
    [
        pa.field("id_reel", pa.string(), nullable=True),
        pa.field("id_comment", pa.string(), nullable=True),
        pa.field("text", pa.string(), nullable=True),
        pa.field("inputUrl", pa.string(), nullable=True),
        pa.field("ownerUsername", pa.string(), nullable=True),
        pa.field("likesCount", pa.int64(), nullable=True),
        pa.field("repliesCount", pa.int64(), nullable=True),
        pa.field("timestamp", pa.string(), nullable=True),
        # ADR 0020 (Ficha 3) / issue #88: discrimina a granularidade da
        # linha -- "comentario" (default, comportamento pré-existente),
        # "legenda" (caption de post/reel) ou "transcricao" (fala do reel,
        # `includeTranscript`). Sem esta coluna, as três fontes ficariam
        # indistinguíveis na mesma tabela (ver `ModelEnricher.write_sentiment`).
        pa.field("fonte", pa.string(), nullable=False),
        pa.field("sentiment_label", pa.string(), nullable=True),
        pa.field("sentiment_score", pa.float64(), nullable=True),
        pa.field("Topic", pa.int64(), nullable=True),
        pa.field("Name", pa.string(), nullable=True),
        pa.field("_run_id", pa.string(), nullable=False),
        pa.field("_generated_at", pa.timestamp("us", tz="UTC"), nullable=False),
    ]
)

# ADR 0020 (Ficha 4) / issue #89: tópicos do discurso oficial (BERTopic
# sobre legenda+transcrição, reaproveitando `model_topics()`) -- tabela Gold
# própria, NÃO uma extensão de `governor_sentiment`: as duas granularidades
# são conceitualmente distintas (fala da assessoria vs. reação do público),
# decisão de schema já fechada na ADR 0020. Colunas equivalentes às de
# tópico de comentário (`Topic`/`Name`/texto-fonte/`ownerUsername`), mais
# `fonte` ("legenda"/"transcricao") para distinguir as duas dentro da
# própria tabela -- mesmo padrão de `GOLD_SENTIMENT_SCHEMA` (issue #88).
GOLD_DISCOURSE_TOPICS_SCHEMA = pa.schema(
    [
        pa.field("id_reel", pa.string(), nullable=True),
        pa.field("text", pa.string(), nullable=True),
        pa.field("inputUrl", pa.string(), nullable=True),
        pa.field("ownerUsername", pa.string(), nullable=True),
        pa.field("timestamp", pa.string(), nullable=True),
        pa.field("fonte", pa.string(), nullable=False),
        pa.field("Topic", pa.int64(), nullable=True),
        pa.field("Name", pa.string(), nullable=True),
        pa.field("_run_id", pa.string(), nullable=False),
        pa.field("_generated_at", pa.timestamp("us", tz="UTC"), nullable=False),
    ]
)

# ADR 0020 (Ficha 2): `content_type` ("reel"/"feed") discrimina a
# granularidade de origem de cada linha -- clusterização de posts do feed
# (issue #87) grava aqui também, em vez de uma tabela `governor_feed_clusters`
# nova (opção rejeitada na ADR: mesma pipeline PCA->AutoClusterHPO, mesma
# granularidade conceitual de post, só as features de entrada do PCA mudam).
# `id_reel` continua com esse nome por compatibilidade com o contrato já
# fechado -- passa a guardar o id do post também quando `content_type=="feed"`.
GOLD_CLUSTERS_SCHEMA = pa.schema(
    [
        pa.field("id_reel", pa.string(), nullable=False),
        pa.field("ownerUsername", pa.string(), nullable=False),
        pa.field("cluster_label", pa.int64(), nullable=False),
        pa.field("cluster_algo", pa.string(), nullable=False),
        pa.field("cluster_score", pa.float64(), nullable=True),
        pa.field("content_type", pa.string(), nullable=False),
        pa.field("_run_id", pa.string(), nullable=False),
        pa.field("_generated_at", pa.timestamp("us", tz="UTC"), nullable=False),
    ]
)

# Clusterização de PERFIL de governador (Fase 2, por Engajamento) -- 1 linha
# por governador, não por reel. Tabela separada de GOLD_CLUSTERS_SCHEMA de
# propósito (ver ADR 0004/0005: não generalizar schema até existir motivo
# real) -- futuros tipos (sentimento, tópico) ganham cada um sua própria
# tabela/schema, em vez de uma coluna "cluster_type" genérica aqui.
GOLD_PROFILE_CLUSTERS_ENGAGEMENT_SCHEMA = pa.schema(
    [
        pa.field("inputUrl", pa.string(), nullable=False),
        pa.field("cluster_label", pa.int64(), nullable=False),
        pa.field("cluster_algo", pa.string(), nullable=False),
        pa.field("cluster_score", pa.float64(), nullable=True),
        pa.field("_run_id", pa.string(), nullable=False),
        pa.field("_generated_at", pa.timestamp("us", tz="UTC"), nullable=False),
    ]
)

# ADR 0019 (parte C): regressão de performance-por-post -- formato longo, uma
# linha por preditor por grupo por execução. Uma tabela por conceito, com
# `grupo` (vídeo/estático) como dimensão, em vez de duplicar dois schemas
# quase idênticos para cada grupo.
GOLD_POST_PERFORMANCE_COEFFICIENTS_SCHEMA = pa.schema(
    [
        pa.field("grupo", pa.string(), nullable=False),
        pa.field("preditor", pa.string(), nullable=False),
        pa.field("coeficiente", pa.float64(), nullable=False),
        pa.field("r2_treino", pa.float64(), nullable=False),
        # Nulo só no caso degenerado de um grupo sem nenhum governador em
        # holdout (amostra pequena demais) -- ver `train_evaluate_group`.
        pa.field("r2_holdout", pa.float64(), nullable=True),
        pa.field("n_treino", pa.int64(), nullable=False),
        pa.field("n_holdout", pa.int64(), nullable=False),
        pa.field("alpha", pa.float64(), nullable=False),
        pa.field("_run_id", pa.string(), nullable=False),
        pa.field("_generated_at", pa.timestamp("us", tz="UTC"), nullable=False),
    ]
)

# Granularidade de post individual -- previsão/resíduo, treino e holdout
# juntos (ver ADR 0019, decisão 9: habilita a "lacuna de execução" do
# dashboard, issue E, sem exigir uma tabela extra só para holdout).
GOLD_POST_PERFORMANCE_PREDICTIONS_SCHEMA = pa.schema(
    [
        pa.field("id", pa.string(), nullable=False),
        pa.field("inputUrl", pa.string(), nullable=True),
        pa.field("grupo", pa.string(), nullable=False),
        pa.field("y_real", pa.float64(), nullable=False),
        pa.field("y_previsto", pa.float64(), nullable=False),
        pa.field("residuo", pa.float64(), nullable=False),
        pa.field("_run_id", pa.string(), nullable=False),
        pa.field("_generated_at", pa.timestamp("us", tz="UTC"), nullable=False),
    ]
)

# ADR 0020 (Ficha 6) / issue #91: `topic_priority_score` -- Score ICE
# (Impacto x Confiança x Facilidade) de priorização de TÓPICOS DE COMENTÁRIO
# (`governor_sentiment`, fonte "comentario"; ver `TopicPriorityScorer`), uma
# linha por tópico. Não confundir com `GOLD_DISCOURSE_TOPICS_SCHEMA` (fala da
# assessoria) -- Score ICE é só sobre o que o público comenta, para responder
# "sobre o que o governador deveria produzir a seguir". `facilidade` é
# gravada como coluna própria (constante nesta v1, ver
# `TopicPriorityScorer.FACILIDADE_V1`) em vez de só embutida no `score`, para
# que o dashboard (issue futura de Frente 2) possa mostrar as três
# componentes separadamente, não só o produto final.
GOLD_TOPIC_PRIORITY_SCORE_SCHEMA = pa.schema(
    [
        pa.field("Topic", pa.int64(), nullable=False),
        pa.field("Name", pa.string(), nullable=True),
        pa.field("n_comentarios", pa.int64(), nullable=False),
        # Proxy de visibilidade do tópico (soma de likesCount+repliesCount
        # dos comentários do tópico) -- NÃO é alcance/views literal, que não
        # existe por comentário em `governor_sentiment`. Ver docstring de
        # `TopicPriorityScorer` para a justificativa completa da escolha.
        pa.field("alcance_topico", pa.int64(), nullable=False),
        pa.field("alcance_normalizado", pa.float64(), nullable=False),
        pa.field("proporcao_sentimento_positivo", pa.float64(), nullable=False),
        pa.field("confianca", pa.float64(), nullable=False),
        pa.field("impacto", pa.float64(), nullable=False),
        pa.field("facilidade", pa.float64(), nullable=False),
        pa.field("score", pa.float64(), nullable=False),
        pa.field("_run_id", pa.string(), nullable=False),
        pa.field("_generated_at", pa.timestamp("us", tz="UTC"), nullable=False),
    ]
)

# ADR 0020 (Ficha 8) / issue #93: `governor_ugc_mentions` -- UGC de criação
# ("Creating" do COBRA). Grão de UMA LINHA POR POST DE UGC, não agregado por
# governador: a agregação (contagem, engajamento médio, % orgânico vs. pago)
# é uma view/query sobre esta tabela (`GovernorUGCAggregator.aggregate_by_governor`),
# não a granularidade de armazenamento -- decisão explícita da issue, mesmo
# raciocínio de GOLD_CLUSTERS_SCHEMA/GOLD_POST_PERFORMANCE_PREDICTIONS_SCHEMA
# (granularidade fina na Gold, agregação calculada em cima). `is_organic`
# (derivado de isPaidPartnership/isAd/isAffiliate) é o campo que separa UGC
# espontâneo de publi paga ANTES de qualquer agregação -- contar publi como
# "apoio espontâneo" infla falsamente o nível "Criar" do funil COBRA-RACE.
GOLD_UGC_MENTIONS_SCHEMA = pa.schema(
    [
        pa.field("id", pa.string(), nullable=True),
        pa.field("shortCode", pa.string(), nullable=True),
        pa.field("governor_username", pa.string(), nullable=True),
        pa.field("authorUsername", pa.string(), nullable=True),
        pa.field("authorIsVerified", pa.bool_(), nullable=False),
        pa.field("caption", pa.string(), nullable=True),
        pa.field("matchTypes", pa.string(), nullable=True),
        pa.field("likesCount", pa.int64(), nullable=False),
        pa.field("commentsCount", pa.int64(), nullable=False),
        pa.field("videoPlayCount", pa.int64(), nullable=True),
        pa.field("is_organic", pa.bool_(), nullable=False),
        pa.field("data_hora", pa.timestamp("us"), nullable=False),
        pa.field("_run_id", pa.string(), nullable=False),
        pa.field("_generated_at", pa.timestamp("us", tz="UTC"), nullable=False),
    ]
)
