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
        pa.field("commentsCount", pa.int64(), nullable=False),
        pa.field("likesCount", pa.int64(), nullable=False),
        pa.field("data_hora", pa.timestamp("us"), nullable=False),
        pa.field("Tipo", pa.string(), nullable=False),
        pa.field("shortCode", pa.string(), nullable=True),
        pa.field("caption", pa.string(), nullable=True),
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
        pa.field("commentsCount", pa.int64(), nullable=False),
        pa.field("likesCount", pa.int64(), nullable=False),
        pa.field("videoPlayCount", pa.int64(), nullable=True),
        pa.field("videoDuration", pa.float64(), nullable=True),
        pa.field("data_hora", pa.timestamp("us"), nullable=False),
        pa.field("Tipo", pa.string(), nullable=False),
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

# GOLD
GOLD_ENGAGEMENT_SCHEMA = pa.schema(
    [
        pa.field("id", pa.string(), nullable=False),
        pa.field("username", pa.string(), nullable=False),
        pa.field("fullName", pa.string(), nullable=True),
        pa.field("followersCount", pa.int32(), nullable=False),
        pa.field("TOTAL ENGAJAMENTO", pa.int64(), nullable=False),
        pa.field("% ENGAJAMENTO", pa.float64(), nullable=False),
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
        pa.field("id", pa.string(), nullable=False),
        pa.field("username", pa.string(), nullable=False),
        pa.field("cluster_label", pa.int64(), nullable=False),
        pa.field("cluster_algo", pa.string(), nullable=False),
        pa.field("cluster_score", pa.float64(), nullable=True),
        pa.field("_run_id", pa.string(), nullable=False),
        pa.field("_generated_at", pa.timestamp("us", tz="UTC"), nullable=False),
    ]
)
