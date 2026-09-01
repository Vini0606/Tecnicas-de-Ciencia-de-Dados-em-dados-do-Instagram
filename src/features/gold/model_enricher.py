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
    ) -> None:
        df = df_comments_with_sentiment.copy()
        df["_run_id"] = run_id
        df["_generated_at"] = datetime.now(timezone.utc)
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
