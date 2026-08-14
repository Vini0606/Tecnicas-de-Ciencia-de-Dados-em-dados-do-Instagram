"""
Silver post and reel cleaner
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pandas as pd

from src.delta_io import write_delta
from src.schemas_delta import SILVER_POSTS_SCHEMA, SILVER_REELS_SCHEMA


class PostCleaner:
    POSTS_COLUMNS_TO_DROP: ClassVar[list[str]] = [
        "hashtags",
        "mentions",
        "images",
        "childPosts",
        "taggedUsers",
        "coauthorProducers",
        "musicInfo",
    ]

    def clean_posts(self, df_bronze: pd.DataFrame) -> pd.DataFrame:
        df = df_bronze.copy()
        df = self._deduplicate(df)
        df = self._parse_timestamp(df)
        df["Tipo"] = "FEED"
        df = self._cast_numerics(df)
        df = self._drop_noise_columns(df)
        df["_source_layer"] = "bronze"
        return df

    def clean_reels(self, df_bronze: pd.DataFrame) -> pd.DataFrame:
        df = df_bronze.copy()
        df = self._deduplicate(df)
        df = self._parse_timestamp(df)
        df["Tipo"] = "REELS"
        df["Total de Engajamento"] = (
            df.get("commentsCount", pd.Series(dtype="int64")).fillna(0)
            + df.get("likesCount", pd.Series(dtype="int64")).fillna(0)
        ).astype("int64")

        if "isPinned" in df.columns:
            df["isPinned"] = df["isPinned"].map(
                lambda v: (
                    v if isinstance(v, bool) else str(v).lower() in ("true", "1", "yes")
                )
            )

        df = self._cast_numerics(df)
        df = self._drop_noise_columns(df)
        df["_source_layer"] = "bronze"
        return df

    def write_posts(self, df_silver: pd.DataFrame, path: Path | str) -> None:
        write_delta(path, df_silver, SILVER_POSTS_SCHEMA)

    def write_reels(self, df_silver: pd.DataFrame, path: Path | str) -> None:
        write_delta(path, df_silver, SILVER_REELS_SCHEMA)

    def _deduplicate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        A camada Bronze é append-only e acumula todas as execuções. Sem esta
        deduplicação, reprocessar o pipeline multiplicaria cada publicação e
        inflaria as métricas de engajamento agregadas na camada Gold.
        """
        if "id" not in df.columns:
            return df
        if "_ingested_at" in df.columns:
            df = df.sort_values("_ingested_at", ascending=False)
        return df.drop_duplicates(subset=["id"], keep="first")

    def _parse_timestamp(self, df: pd.DataFrame) -> pd.DataFrame:
        if "timestamp" in df.columns:
            df["data_hora"] = (
                pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
                .dt.tz_convert("America/Sao_Paulo")
                .dt.tz_localize(None)
            )
        return df

    def _cast_numerics(self, df: pd.DataFrame) -> pd.DataFrame:
        int64_cols = ["commentsCount", "likesCount", "videoPlayCount", "videoViewCount"]
        for col in int64_cols:
            if col in df.columns:
                df[col] = (
                    pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64")
                )
        return df

    def _drop_noise_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        cols = [c for c in self.POSTS_COLUMNS_TO_DROP if c in df.columns]
        return df.drop(columns=cols)
