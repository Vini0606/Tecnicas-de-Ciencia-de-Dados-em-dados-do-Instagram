"""
Gold model enricher
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.delta_io import write_delta
from src.schemas_delta import GOLD_CLUSTERS_SCHEMA, GOLD_SENTIMENT_SCHEMA


class ModelEnricher:
    def write_sentiment(
        self, df_comments_with_sentiment: pd.DataFrame, path: Path | str, run_id: str
    ) -> None:
        df = df_comments_with_sentiment.copy()
        df["_run_id"] = run_id
        df["_generated_at"] = datetime.now(timezone.utc)
        write_delta(path, df, GOLD_SENTIMENT_SCHEMA)

    def write_clusters(
        self,
        df_profiles_silver: pd.DataFrame,
        cluster_labels,
        algo_name: str,
        best_score: float,
        path: Path | str,
        run_id: str,
    ) -> None:
        df_clusters = pd.DataFrame(
            {
                "id": df_profiles_silver["id"].values,
                "username": df_profiles_silver["username"].values,
                "cluster_label": cluster_labels.astype("int64"),
                "cluster_algo": algo_name,
                "cluster_score": float(best_score),
                "_run_id": run_id,
                "_generated_at": datetime.now(timezone.utc),
            }
        )
        write_delta(path, df_clusters, GOLD_CLUSTERS_SCHEMA)
