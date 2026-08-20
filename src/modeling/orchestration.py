"""Orquestração da modelagem: estágio determinístico e refinamento via Gemini"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from bertopic import BERTopic

from src.features.gold.model_enricher import ModelEnricher
from src.modeling.clustering import cluster_reels
from src.modeling.config import GeminiRefinerConfig, ModelingConfig
from src.modeling.gemini_refiner import apply_gemini_refinement
from src.modeling.pca import reduce_dimensions
from src.modeling.preprocessing import preprocess_comments
from src.modeling.sentiment import analyze_sentiment
from src.modeling.topics import model_topics
from src.run_id import build_run_id


@dataclass
class DeterministicModelingResult:
    df_reels: pd.DataFrame
    df_comments: pd.DataFrame
    topic_model: BERTopic
    pca_model: object
    cluster_model: object
    cluster_config: dict | None
    cluster_score: float
    cluster_algo_name: str | None
    docs: list[str]
    run_id: str


def _merge_topic_info(df_comments: pd.DataFrame, document_info: pd.DataFrame) -> pd.DataFrame:
    """Reproduz a junção feita no notebook 03: concatena por posição (não por
    índice) o `document_info` do BERTopic ao DataFrame de comentários, na
    mesma ordem de `docs`, e descarta a coluna `Document` (já redundante com
    `text_demojized`)."""
    df_reset = df_comments.reset_index(drop=True)
    info_reset = document_info.reset_index(drop=True)
    return pd.concat([df_reset, info_reset], axis=1).drop(columns=["Document"])


def run_deterministic_modeling(
    df_reels: pd.DataFrame,
    df_comments: pd.DataFrame,
    config: ModelingConfig,
    run_id: str | None = None,
) -> DeterministicModelingResult:
    """Estágio 100% automatizável: PCA -> clustering -> sentimento -> tópicos
    (representação determinística via KeyBERTInspired, não via Gemini).
    Escreve as duas tabelas Gold (clusters e sentimento/tópicos provisórios)
    sob um único `run_id` novo."""
    run_id = build_run_id(run_id)

    df_reels_pca, pca_model = reduce_dimensions(df_reels, config.pca)
    df_reels_clustered, cluster_model, cluster_config, cluster_score, cluster_algo_name = (
        cluster_reels(df_reels_pca, config.cluster)
    )

    df_comments_sentiment = analyze_sentiment(df_comments, config.sentiment)
    df_comments_preprocessed = preprocess_comments(df_comments_sentiment, config.preprocessing)

    docs = list(df_comments_preprocessed["text_demojized"])
    topic_model, _topics, _probs, document_info = model_topics(docs, config.topics)

    df_comments_final = _merge_topic_info(df_comments_preprocessed, document_info)

    enricher = ModelEnricher()
    enricher.write_clusters(df_reels_clustered, config.gold_clusters_path, run_id)
    enricher.write_sentiment(df_comments_final, config.gold_sentiment_path, run_id)

    return DeterministicModelingResult(
        df_reels=df_reels_clustered,
        df_comments=df_comments_final,
        topic_model=topic_model,
        pca_model=pca_model,
        cluster_model=cluster_model,
        cluster_config=cluster_config,
        cluster_score=cluster_score,
        cluster_algo_name=cluster_algo_name,
        docs=docs,
        run_id=run_id,
    )


@dataclass
class GeminiRefinementResult:
    df_comments: pd.DataFrame
    topic_model: BERTopic
    run_id: str


def refine_topics_with_gemini(
    topic_model: BERTopic,
    docs: list[str],
    df_comments: pd.DataFrame,
    config: GeminiRefinerConfig,
    run_id: str | None = None,
) -> GeminiRefinementResult:
    """Reescreve só os rótulos de tópico (`Topic`/`Name`) de `df_comments`
    com o refinamento manual via Gemini, sob um `run_id` novo — não mexe em
    `governor_clusters`, que não depende do refinamento de tópicos.

    `df_comments` deve ser o `df_comments` retornado por
    `run_deterministic_modeling` (mesma ordem de linhas que `docs`)."""
    run_id = build_run_id(run_id)

    apply_gemini_refinement(topic_model, docs, config)
    refreshed_info = topic_model.get_document_info(docs).reset_index(drop=True)

    df_comments_refined = df_comments.reset_index(drop=True).copy()
    df_comments_refined["Topic"] = refreshed_info["Topic"].values
    df_comments_refined["Name"] = refreshed_info["Name"].values

    ModelEnricher().write_sentiment(df_comments_refined, config.gold_sentiment_path, run_id)

    return GeminiRefinementResult(
        df_comments=df_comments_refined, topic_model=topic_model, run_id=run_id
    )
