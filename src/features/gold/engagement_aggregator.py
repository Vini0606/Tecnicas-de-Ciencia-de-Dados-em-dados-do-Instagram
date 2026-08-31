"""
Gold engagement aggregator
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.delta_io import write_delta
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

        # O merge é left: perfis sem publicações correspondentes chegam com
        # NaN nestes agregados, que o contrato Gold declara como não-anuláveis.
        for column in ("commentsSum", "likesSum", "count"):
            df[column] = df[column].fillna(0).astype("int64")

        df["TOTAL ENGAJAMENTO"] = (df["commentsSum"] + df["likesSum"]).astype("int64")

        followers = pd.to_numeric(df["followersCount"], errors="coerce").astype("float64")
        df["% ENGAJAMENTO"] = (
            df["TOTAL ENGAJAMENTO"].div(followers.where(followers > 0)).fillna(0.0)
        )

        if "maxData" in df.columns:
            max_data = df["maxData"].max()
            dias_desde_ultimo = (max_data - df["maxData"]).dt.days
            # Perfil sem publicações tem maxData nulo. Sem o tratamento
            # explícito, o fillna(0) o classificaria como o mais recente
            # possível — ausência de dados viraria recência máxima.
            df["RECENCIA"] = (1.0 / (dias_desde_ultimo + 1)).fillna(0.0)
        else:
            df["RECENCIA"] = 0.0

        if "maxData" in df.columns and "minData" in df.columns:
            dias_ativos = (df["maxData"] - df["minData"]).dt.days + 1
            df["FREQUENCIA"] = (df["count"] / dias_ativos).fillna(0.0)
        else:
            df["FREQUENCIA"] = 0.0

        df["_run_id"] = run_id
        df["_generated_at"] = datetime.now(timezone.utc)

        return df

    def write(self, df_gold: pd.DataFrame, path: Path | str, mode: str = "overwrite") -> None:
        write_delta(path, df_gold, GOLD_ENGAGEMENT_SCHEMA, mode=mode)
