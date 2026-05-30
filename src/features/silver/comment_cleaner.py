"""
Silver comment cleaner
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from deltalake.writer import write_deltalake

from src.schemas_delta import SILVER_COMMENTS_SCHEMA


class CommentCleaner:
    MAX_TEXT_LENGTH = 512
    COLUMNS_TO_DROP = [
        "hashtags",
        "mentions",
        "images",
        "childPosts",
        "musicInfo",
        "replies",
        "taggedUsers",
        "coauthorProducers",
    ]

    def clean(self, df_reels_bronze: pd.DataFrame) -> pd.DataFrame:
        if "latestComments" not in df_reels_bronze.columns:
            return pd.DataFrame()

        df = df_reels_bronze.copy()
        df["latestComments"] = df["latestComments"].apply(
            lambda v: json.loads(v) if isinstance(v, str) else (v or [])
        )

        df_exploded = df.explode("latestComments").copy()
        df_exploded = df_exploded[df_exploded["latestComments"].notna()]

        df_normalized = pd.json_normalize(
            df_exploded["latestComments"].apply(
                lambda x: x if isinstance(x, dict) else {}
            )
        )
        df_normalized.index = df_exploded.index

        df_result = df_exploded.drop("latestComments", axis=1).join(
            df_normalized, lsuffix="_reel", rsuffix="_comment"
        )

        if "text" not in df_result.columns:
            df_result["text"] = ""

        cols_to_drop = [c for c in self.COLUMNS_TO_DROP if c in df_result.columns]
        if cols_to_drop:
            df_result = df_result.drop(columns=cols_to_drop)
        df_result["comprimento texto"] = df_result["text"].astype(str).str.len()
        df_result = df_result[df_result["comprimento texto"] < self.MAX_TEXT_LENGTH]
        df_result = df_result.drop_duplicates()
        df_result["_source_layer"] = "bronze"

        return df_result

    def write(self, df_silver: pd.DataFrame, path: Path | str) -> None:
        write_deltalake(
            str(path),
            df_silver,
            mode="overwrite",
            schema=SILVER_COMMENTS_SCHEMA,
            schema_mode="overwrite",
        )
