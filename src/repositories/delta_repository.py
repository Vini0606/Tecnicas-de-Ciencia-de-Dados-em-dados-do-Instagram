"""
DeltaRepository implementation
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from deltalake import DeltaTable

from src.repositories.base import DataRepository


class DeltaRepository(DataRepository):
    def __init__(
        self,
        gold_dir: Path | str,
        silver_dir: Path | None = None,
        as_of_version: int | None = None,
        as_of_timestamp: str | None = None,
        storage_options: dict | None = None,
    ):
        self._gold_dir = Path(gold_dir)
        self._silver_dir = Path(silver_dir) if silver_dir is not None else None
        self._as_of_version = as_of_version
        self._as_of_timestamp = as_of_timestamp
        self._storage_options = storage_options or {}

    def load_profiles(self) -> pd.DataFrame:
        return self._load(self._gold_dir / "governor_engagement")

    def load_posts(self) -> pd.DataFrame:
        if self._silver_dir is None:
            raise ValueError("silver_dir não foi configurado neste repositório.")
        return self._load(self._silver_dir / "posts_clean")

    def load_reels(self) -> pd.DataFrame:
        if self._silver_dir is None:
            raise ValueError("silver_dir não foi configurado neste repositório.")
        return self._load(self._silver_dir / "reels_clean")

    def load_comments(self) -> pd.DataFrame:
        try:
            return self._load(self._gold_dir / "governor_sentiment")
        except FileNotFoundError:
            if self._silver_dir is None:
                raise
            return self._load(self._silver_dir / "comments_clean")

    def load_clusters(self) -> pd.DataFrame:
        return self._load(self._gold_dir / "governor_clusters")

    def save(self, dataframes: dict[str, pd.DataFrame]) -> None:
        raise NotImplementedError(
            "DeltaRepository é somente leitura. Use os writers para escrever."
        )

    def get_table_history(self, table_name: str) -> pd.DataFrame:
        dt = DeltaTable(
            str(self._gold_dir / table_name), storage_options=self._storage_options
        )
        return pd.DataFrame(dt.history())

    def _load(self, path: Path) -> pd.DataFrame:
        try:
            dt = DeltaTable(str(path), storage_options=self._storage_options)
            if self._as_of_version is not None:
                return dt.load_as_version(self._as_of_version).to_pandas()
            if self._as_of_timestamp is not None:
                return dt.load_with_datetime(self._as_of_timestamp).to_pandas()
            return dt.to_pandas()
        except Exception as e:
            raise FileNotFoundError(
                f"Tabela Delta não encontrada em {path}. Execute o pipeline Medallion primeiro. Detalhe: {e}"
            ) from e
