"""
Silver profile cleaner
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pandas as pd

from src.delta_io import deduplicate_latest, write_delta
from src.schemas_delta import SILVER_PROFILES_SCHEMA


class ProfileCleaner:
    COLUMNS_TO_DROP: ClassVar[list[str]] = [
        "businessAddress",
        "externalUrl",
        "externalUrlShimmed",
        "biography",
        "highlightReelCount",
        "url",
        "profilePicUrl",
        "profilePicUrlHD",
        "fbid",
    ]

    INT32_COLUMNS: ClassVar[list[str]] = ["followersCount", "followsCount", "postsCount", "igtvVideoCount"]
    BOOL_COLUMNS: ClassVar[list[str]] = [
        "verified",
        "private",
        "isBusinessAccount",
        "hasChannel",
        "joinedRecently",
    ]

    def clean(self, df_bronze: pd.DataFrame, run_id: str) -> pd.DataFrame:
        df = df_bronze.copy()
        cols_to_drop = [c for c in self.COLUMNS_TO_DROP if c in df.columns]
        if cols_to_drop:
            df = df.drop(columns=cols_to_drop)

        for col in self.INT32_COLUMNS:
            if col in df.columns:
                df[col] = (
                    pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int32")
                )

        for col in self.BOOL_COLUMNS:
            if col in df.columns:
                df[col] = df[col].fillna(False).astype(bool)

        df = deduplicate_latest(df, id_col="id")

        if "fullName" not in df.columns:
            if "username" in df.columns:
                df["fullName"] = df["username"]
            elif "inputUrl" in df.columns:
                df["fullName"] = df["inputUrl"]
            else:
                df["fullName"] = pd.NA

        df["_source_layer"] = "bronze"

        return df

    def write(self, df_silver: pd.DataFrame, path: Path | str) -> None:
        write_delta(path, df_silver, SILVER_PROFILES_SCHEMA)
