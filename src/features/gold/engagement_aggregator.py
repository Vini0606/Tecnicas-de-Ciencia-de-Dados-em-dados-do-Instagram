"""
Gold engagement aggregator
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from deltalake.writer import write_deltalake

from src.schemas_delta import GOLD_ENGAGEMENT_SCHEMA


class EngagementAggregator:
    def aggregate(
        self,
        df_profiles_silver: pd.DataFrame,
        df_posts_silver: pd.DataFrame,
        df_reels_silver: pd.DataFrame,
        run_id: str,
    ) -> pd.DataFrame:
        df_combined = pd.concat([df_posts_silver, df_reels_silver], axis=0)

        grouped = (
            df_combined.groupby(["ownerId", "ownerUsername"])
            .agg(
                commentsSum=("commentsCount", "sum"),
                likesSum=("likesCount", "sum"),
                minData=("data_hora", "min"),
                maxData=("data_hora", "max"),
                count=("ownerId", "count"),
            )
            .reset_index()
        )

        df = pd.merge(
            df_profiles_silver,
            grouped,
            left_on="id",
            right_on="ownerId",
            how="left",
        ).drop(columns=["ownerId"], errors="ignore")

        df["TOTAL ENGAJAMENTO"] = (
            df["commentsSum"].fillna(0) + df["likesSum"].fillna(0)
        ).astype("int64")

        df["% ENGAJAMENTO"] = (
            df["TOTAL ENGAJAMENTO"] / df["followersCount"].replace(0, pd.NA)
        ).fillna(0.0)

        if "maxData" in df.columns:
            max_data = df["maxData"].max()
            df["RECENCIA"] = 1.0 / ((max_data - df["maxData"]).dt.days.fillna(0) + 1)
        else:
            df["RECENCIA"] = 0.0

        if "maxData" in df.columns and "minData" in df.columns:
            active_days = (df["maxData"] - df["minData"]).dt.days.fillna(0) + 1
            df["FREQUENCIA"] = df["count"].fillna(0) / active_days
        else:
            df["FREQUENCIA"] = 0.0

        df["_run_id"] = run_id
        df["_generated_at"] = datetime.now(timezone.utc)

        return df

    def write(self, df_gold: pd.DataFrame, path: Path | str) -> None:
        write_deltalake(
            str(path),
            df_gold,
            mode="overwrite",
            schema=GOLD_ENGAGEMENT_SCHEMA,
            schema_mode="overwrite",
        )
