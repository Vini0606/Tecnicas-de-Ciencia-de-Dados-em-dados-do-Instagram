"""
Silver post and reel cleaner
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import ClassVar

import pandas as pd

from src.delta_io import deduplicate_latest, write_delta
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
        df = deduplicate_latest(df, id_col="id")
        df = self._parse_timestamp(df)
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
        df = deduplicate_latest(df, id_col="id")
        df = self._parse_timestamp(df)
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

    def _parse_timestamp(self, df: pd.DataFrame) -> pd.DataFrame:
        if "timestamp" in df.columns:
            # format="ISO8601" -- sem isso, pd.to_datetime infere o formato a
            # partir do primeiro valor da série e aplica esse formato pra
            # série inteira; um único timestamp sem timezone misturado com o
            # restante (com timezone, formato real do Apify) faz quase todos
            # os outros virarem NaT silenciosamente. Isso derruba a escrita
            # da Silver inteira, já que `data_hora` é NOT NULL no schema --
            # e numa Bronze acumulando muitos run_id (ADR 0011), basta um
            # registro com timestamp em formato diferente pra travar tudo.
            df["data_hora"] = (
                pd.to_datetime(df["timestamp"], errors="coerce", utc=True, format="ISO8601")
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
                    "extração, ver landing zone do run_id para o payload bruto)%s",
                    len(sem_id),
                    entity,
                    f" -- perfis afetados: {owners}" if owners else "",
                )
            df = df[df["id"].notna()]
        return df

    def _filter_delisted_governors(
        self, df: pd.DataFrame, governor_usernames: list[str] | None
    ) -> pd.DataFrame:
        # Achado real (PR #137): a Bronze é append-only e nunca esquece um
        # `id` -- sem este filtro, um governador removido de
        # governadores.xlsx continua reaparecendo indefinidamente com o
        # último post/reel real, cada vez mais desatualizado.
        # `governor_usernames=None` preserva o comportamento antigo (sem
        # filtro) -- usado pelos testes unitários deste cleaner.
        if governor_usernames is not None and "ownerUsername" in df.columns:
            df = df[df["ownerUsername"].isin(governor_usernames)]
        return df
