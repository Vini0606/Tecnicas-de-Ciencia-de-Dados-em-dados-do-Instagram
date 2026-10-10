"""
Silver post and reel cleaner
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import ClassVar

import pandas as pd

from src.delta_io import write_delta
from src.features.silver.parsing import (
    drop_duplicate_ids,
    drop_invalid_timestamp,
    parse_timestamp_sp,
    to_numeric_logged,
)
from src.schemas_delta import SILVER_POSTS_SCHEMA, SILVER_REELS_SCHEMA

logger = logging.getLogger(__name__)


class PostCleaner:
    POSTS_COLUMNS_TO_DROP: ClassVar[list[str]] = [
        "mentions",
        "images",
        "childPosts",
        "taggedUsers",
        "coauthorProducers",
        "musicInfo",
    ]

    def clean_posts(
        self, df_bronze: pd.DataFrame, governor_usernames: list[str] | None = None
    ) -> pd.DataFrame:
        df = df_bronze.copy()
        df = self._drop_null_id(df, entity="post")
        df = self._filter_delisted_governors(df, governor_usernames)
        df = drop_duplicate_ids(df, "id", "post")
        df = self._parse_timestamp(df, entity="post")
        df = self._preserve_type_raw(df)
        df["Tipo"] = "FEED"
        df = self._cast_numerics(df)
        df = self._drop_noise_columns(df)
        df["_source_layer"] = "bronze"
        return df

    def clean_reels(
        self, df_bronze: pd.DataFrame, governor_usernames: list[str] | None = None
    ) -> pd.DataFrame:
        df = df_bronze.copy()
        df = self._drop_null_id(df, entity="reel")
        df = self._filter_delisted_governors(df, governor_usernames)
        df = drop_duplicate_ids(df, "id", "reel")
        df = self._parse_timestamp(df, entity="reel")
        df = self._preserve_type_raw(df)
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

    def _preserve_type_raw(self, df: pd.DataFrame) -> pd.DataFrame:
        # Preserva o campo bruto `type` do Apify (Image/Video/Sidecar) como
        # `type_raw`, antes de `Tipo` (FEED/REELS) ser atribuído logo abaixo
        # -- sem isso, a granularidade original se perde (ADR 0019, parte A:
        # é o preditor de Formato da regressão de performance-por-post). Se
        # `type` não vier no Bronze, o método não cria `type_raw` -- quem
        # preenche o nulo na escrita é `conform_to_schema`.
        if "type" in df.columns:
            df = df.rename(columns={"type": "type_raw"})
        return df

    def _parse_timestamp(self, df: pd.DataFrame, entity: str) -> pd.DataFrame:
        # `data_hora` é NOT NULL no contrato Silver. Timestamp ilegível ou
        # ausente gera warning e REJEITA a linha, em vez de derrubar a
        # escrita inteira (nem sumir em silêncio). format="ISO8601" evita a
        # inferência de formato pelo primeiro valor da série.
        if "timestamp" in df.columns:
            df["data_hora"] = parse_timestamp_sp(df["timestamp"], entity)
            df = drop_invalid_timestamp(df, entity)
        return df

    def _cast_numerics(self, df: pd.DataFrame) -> pd.DataFrame:
        int64_cols = ["commentsCount", "likesCount", "videoPlayCount", "videoViewCount"]
        for col in int64_cols:
            if col in df.columns:
                df[col] = to_numeric_logged(df[col], col, "post/reel").fillna(0).astype("int64")
        return df

    def _drop_noise_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        cols = [c for c in self.POSTS_COLUMNS_TO_DROP if c in df.columns]
        return df.drop(columns=cols)

    def _drop_null_id(self, df: pd.DataFrame, entity: str) -> pd.DataFrame:
        # Apify ocasionalmente retorna um post/reel sem `id` (item indisponível/
        # erro parcial no scrape) -- SILVER_POSTS_SCHEMA/SILVER_REELS_SCHEMA
        # exigem `id` não nulo, então uma linha assim quebraria a escrita da
        # Silver inteira em vez de só descartar o registro inválido.
        if "id" in df.columns:
            sem_id = df[df["id"].isna()]
            if not sem_id.empty:
                owners = (
                    sem_id["ownerUsername"].dropna().unique().tolist()
                    if "ownerUsername" in sem_id.columns
                    else []
                )
                logger.warning(
                    "Descartando %d %s(s) sem `id` (erro/indisponibilidade da Apify na "
                    "extração, ver a coluna `_raw` da Bronze para o payload bruto)%s",
                    len(sem_id),
                    entity,
                    f" -- perfis afetados: {owners}" if owners else "",
                )
            df = df[df["id"].notna()]
        return df

    def _filter_delisted_governors(
        self, df: pd.DataFrame, governor_usernames: list[str] | None
    ) -> pd.DataFrame:
        # Governador removido de governadores.xlsx pode constar na Coleta
        # (Recorte mais amplo ou Coleta herdada) -- o filtro mantém só quem
        # está na planilha atual.
        # `governor_usernames=None` preserva o comportamento antigo (sem
        # filtro) -- usado pelos testes unitários deste cleaner.
        if governor_usernames is not None and "ownerUsername" in df.columns:
            df = df[df["ownerUsername"].isin(governor_usernames)]
        return df
