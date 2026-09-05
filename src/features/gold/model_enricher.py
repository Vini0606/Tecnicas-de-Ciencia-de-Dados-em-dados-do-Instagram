"""
Gold model enricher
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.delta_io import write_delta
from src.schemas_delta import (
    GOLD_CLUSTERS_SCHEMA,
    GOLD_POST_PERFORMANCE_COEFFICIENTS_SCHEMA,
    GOLD_POST_PERFORMANCE_PREDICTIONS_SCHEMA,
    GOLD_PROFILE_CLUSTERS_ENGAGEMENT_SCHEMA,
    GOLD_SENTIMENT_SCHEMA,
)


class ModelEnricher:
    def write_sentiment(
        self,
        df_comments_with_sentiment: pd.DataFrame,
        path: Path | str,
        run_id: str,
        mode: str = "overwrite",
        generated_at: datetime | None = None,
    ) -> None:
        df = df_comments_with_sentiment.copy()
        df["_run_id"] = run_id
        # `generated_at` explícito (issue #52) para que duas chamadas desta
        # função para o mesmo run -- governor_sentiment e
        # governor_sentiment_history -- carimbem o mesmo timestamp, em vez
        # de dois `datetime.now()` levemente diferentes.
        df["_generated_at"] = generated_at or datetime.now(timezone.utc)
        write_delta(path, df, GOLD_SENTIMENT_SCHEMA, mode=mode)

    def write_clusters(
        self,
        df_reels_clustered: pd.DataFrame,
        path: Path | str,
        run_id: str,
    ) -> None:
        """Grava clusters de reels (AutoClusterHPO). Espera as colunas
        produzidas pelo notebook 03: id, ownerUsername, 'Clusters (AutoClusterHPO)',
        algo_name, score."""
        required = {"id", "ownerUsername", "Clusters (AutoClusterHPO)", "algo_name", "score"}
        missing = required - set(df_reels_clustered.columns)
        if missing:
            raise ValueError(
                f"df_reels_clustered não tem as colunas esperadas: {sorted(missing)}"
            )

        df_clusters = pd.DataFrame(
            {
                "id_reel": df_reels_clustered["id"].values,
                "ownerUsername": df_reels_clustered["ownerUsername"].values,
                "cluster_label": df_reels_clustered["Clusters (AutoClusterHPO)"]
                .astype("int64")
                .values,
                "cluster_algo": df_reels_clustered["algo_name"].astype(str).values,
                "cluster_score": df_reels_clustered["score"].astype(float).values,
                "_run_id": run_id,
                "_generated_at": datetime.now(timezone.utc),
            }
        )
        write_delta(path, df_clusters, GOLD_CLUSTERS_SCHEMA)

    def write_profile_clusters_engagement(
        self,
        df_profiles_clustered: pd.DataFrame,
        path: Path | str,
        run_id: str,
    ) -> None:
        """Grava clusters de PERFIL de governador por Engajamento (Fase 2).
        Espera as mesmas colunas de saída de `run_autocluster`/
        `cluster_governor_profiles`: inputUrl, 'Clusters (AutoClusterHPO)',
        algo_name, score. Granularidade de governador, não de reel -- schema
        e path são deliberadamente separados de `write_clusters`."""
        required = {"inputUrl", "Clusters (AutoClusterHPO)", "algo_name", "score"}
        missing = required - set(df_profiles_clustered.columns)
        if missing:
            raise ValueError(
                f"df_profiles_clustered não tem as colunas esperadas: {sorted(missing)}"
            )

        df_clusters = pd.DataFrame(
            {
                "inputUrl": df_profiles_clustered["inputUrl"].values,
                "cluster_label": df_profiles_clustered["Clusters (AutoClusterHPO)"]
                .astype("int64")
                .values,
                "cluster_algo": df_profiles_clustered["algo_name"].astype(str).values,
                "cluster_score": df_profiles_clustered["score"].astype(float).values,
                "_run_id": run_id,
                "_generated_at": datetime.now(timezone.utc),
            }
        )
        write_delta(path, df_clusters, GOLD_PROFILE_CLUSTERS_ENGAGEMENT_SCHEMA)

    def write_post_performance_coefficients(
        self,
        df_coefficients: pd.DataFrame,
        path: Path | str,
        run_id: str,
    ) -> None:
        """Grava coeficientes+R² da regressão de performance-por-post (ADR
        0019, parte C). Espera as colunas produzidas por
        `run_post_performance_stage`: grupo, preditor, coeficiente,
        r2_treino, r2_holdout, n_treino, n_holdout, alpha."""
        required = {
            "grupo",
            "preditor",
            "coeficiente",
            "r2_treino",
            "r2_holdout",
            "n_treino",
            "n_holdout",
            "alpha",
        }
        missing = required - set(df_coefficients.columns)
        if missing:
            raise ValueError(
                f"df_coefficients não tem as colunas esperadas: {sorted(missing)}"
            )

        df = df_coefficients.copy()
        df["_run_id"] = run_id
        df["_generated_at"] = datetime.now(timezone.utc)
        write_delta(path, df, GOLD_POST_PERFORMANCE_COEFFICIENTS_SCHEMA)

    def write_post_performance_predictions(
        self,
        df_predictions: pd.DataFrame,
        path: Path | str,
        run_id: str,
    ) -> None:
        """Grava previsão/resíduo por post da regressão de
        performance-por-post (ADR 0019, parte C). Espera as colunas
        produzidas por `run_post_performance_stage`: id, inputUrl, grupo,
        y_real, y_previsto, residuo."""
        required = {"id", "inputUrl", "grupo", "y_real", "y_previsto", "residuo"}
        missing = required - set(df_predictions.columns)
        if missing:
            raise ValueError(
                f"df_predictions não tem as colunas esperadas: {sorted(missing)}"
            )

        df = df_predictions.copy()
        df["_run_id"] = run_id
        df["_generated_at"] = datetime.now(timezone.utc)
        write_delta(path, df, GOLD_POST_PERFORMANCE_PREDICTIONS_SCHEMA)
