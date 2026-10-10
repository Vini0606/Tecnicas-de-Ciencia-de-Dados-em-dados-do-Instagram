"""
Silver comment cleaner
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import ClassVar, Literal

import pandas as pd

from src.delta_io import write_delta
from src.features.silver.parsing import drop_duplicate_ids
from src.schemas_delta import SILVER_COMMENTS_SCHEMA, SILVER_POST_COMMENTS_SCHEMA

logger = logging.getLogger(__name__)

_SCHEMA_POR_ORIGEM = {"reel": SILVER_COMMENTS_SCHEMA, "post": SILVER_POST_COMMENTS_SCHEMA}


def _parse_latest_comments(valor):
    """Lista de comentarios; `None` sinaliza JSON invalido (o chamador avisa)."""
    if isinstance(valor, str):
        try:
            parsed = json.loads(valor)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, list) else None
    return valor or []


class CommentCleaner:
    """Explode `latestComments` da Bronze de reels (`origem="reel"`, padrão,
    grava `comments_clean` com `id_reel`) ou de posts de feed (`origem=
    "post"`, issue #212, grava `post_comments_clean` com `id_post`). Mesmas
    regras para as duas origens."""

    MAX_TEXT_LENGTH = 512
    COLUMNS_TO_DROP: ClassVar[list[str]] = [
        "hashtags",
        "mentions",
        "images",
        "childPosts",
        "musicInfo",
        "replies",
        "taggedUsers",
        "coauthorProducers",
    ]

    def __init__(self, origem: Literal["reel", "post"] = "reel"):
        if origem not in _SCHEMA_POR_ORIGEM:
            raise ValueError(f"origem desconhecida: {origem!r} (use 'reel' ou 'post')")
        self._origem = origem

    def clean(
        self,
        df_reels_bronze: pd.DataFrame,
        governor_usernames: list[str] | None = None,
    ) -> pd.DataFrame:
        if "latestComments" not in df_reels_bronze.columns:
            return pd.DataFrame()

        df = df_reels_bronze.copy()

        # Filtra pelo `ownerUsername` do REEL (o
        # governador) ANTES do explode/join abaixo -- depois deles,
        # `ownerUsername` passa a se referir ao autor do COMENTÁRIO, não ao
        # governador (ver `_promote_comment_columns`). `governor_usernames=
        # None` preserva o comportamento antigo (sem filtro), usado pelos
        # testes unitários deste cleaner.
        if governor_usernames is not None and "ownerUsername" in df.columns:
            df = df[df["ownerUsername"].isin(governor_usernames)]

        df["latestComments"] = df["latestComments"].apply(_parse_latest_comments)
        invalidos = df["latestComments"].isna()
        if invalidos.any():
            logger.warning(
                "%d %s(s) com `latestComments` em JSON invalido -- comentarios "
                "desses itens ignorados (payload original na coluna `_raw` da Bronze): %s",
                int(invalidos.sum()),
                self._origem,
                df.loc[invalidos, "id"].astype(str).tolist()[:10] if "id" in df.columns else [],
            )
            df["latestComments"] = df["latestComments"].apply(
                lambda v: [] if not isinstance(v, list) else v
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
            df_normalized, lsuffix=f"_{self._origem}", rsuffix="_comment"
        )

        if "text" not in df_result.columns:
            df_result["text"] = ""

        df_result = self._promote_comment_columns(df_result)

        cols_to_drop = [c for c in self.COLUMNS_TO_DROP if c in df_result.columns]
        if cols_to_drop:
            df_result = df_result.drop(columns=cols_to_drop)
        df_result["comprimento texto"] = df_result["text"].astype(str).str.len()
        df_result = df_result[df_result["comprimento texto"] < self.MAX_TEXT_LENGTH]
        df_result = drop_duplicate_ids(df_result, "id_comment", "comentario")
        df_result["_source_layer"] = "bronze"

        return df_result

    def _promote_comment_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        O join entre reel e comentário sufixa as colunas homônimas com
        `_reel` e `_comment`. Estes campos descrevem o comentário, não o
        reel, então a variante `_comment` é promovida ao nome sem sufixo
        esperado por SILVER_COMMENTS_SCHEMA.
        """
        for column in ("ownerUsername", "likesCount", "timestamp"):
            suffixed = f"{column}_comment"
            if suffixed in df.columns:
                df[column] = df[suffixed]
        return df

    def write(self, df_silver: pd.DataFrame, path: Path | str) -> None:
        write_delta(path, df_silver, _SCHEMA_POR_ORIGEM[self._origem])
