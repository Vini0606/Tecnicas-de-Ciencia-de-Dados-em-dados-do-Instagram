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
        pa.field("sentiment_label", pa.string(), nullable=True),
        pa.field("sentiment_score", pa.float64(), nullable=True),
        pa.field("Topic", pa.int64(), nullable=True),
        pa.field("Name", pa.string(), nullable=True),
        pa.field("_run_id", pa.string(), nullable=False),
        pa.field("_generated_at", pa.timestamp("us", tz="UTC"), nullable=False),
    ]
)

GOLD_CLUSTERS_SCHEMA = pa.schema(
    [
        pa.field("id_reel", pa.string(), nullable=False),
        pa.field("ownerUsername", pa.string(), nullable=False),
        pa.field("cluster_label", pa.int64(), nullable=False),
        pa.field("cluster_algo", pa.string(), nullable=False),
        pa.field("cluster_score", pa.float64(), nullable=True),
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
