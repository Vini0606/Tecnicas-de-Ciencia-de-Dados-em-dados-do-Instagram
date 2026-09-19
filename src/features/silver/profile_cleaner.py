"""
Silver profile cleaner
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import ClassVar

import pandas as pd

from src.delta_io import deduplicate_latest, write_delta
from src.schemas_delta import SILVER_PROFILES_SCHEMA

logger = logging.getLogger(__name__)


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

        # Apify ocasionalmente retorna um resultado de scrape sem `id` (perfil
        # indisponível/erro parcial) -- SILVER_PROFILES_SCHEMA exige `id` não
        # nulo, então uma linha assim quebraria a escrita da Silver inteira
        # em vez de só descartar o registro inválido.
        if "id" in df.columns:
            sem_id = df[df["id"].isna()]
            if not sem_id.empty:
                usernames = (
                    sem_id["username"].dropna().tolist() if "username" in sem_id.columns else []
                )
                logger.warning(
                    "Descartando %d perfil(is) sem `id` (erro/indisponibilidade da Apify na "
                    "extração, ver landing zone do run_id para o payload bruto): %s",
                    len(sem_id),
                    usernames or "[username também ausente]",
                )
            df = df[df["id"].notna()]

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
                # .astype("boolean") antes do fillna evita o FutureWarning de
                # downcast implícito do pandas em coluna dtype=object --
                # mesmo achado de UGCMentionCleaner._cast_bools (2026-09-19),
                # mesma causa (coluna mista True/False/None vinda do JSON
                # bruto da Apify).
                df[col] = df[col].astype("boolean").fillna(False).astype(bool)

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
