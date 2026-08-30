"""
Silver governors metadata cleaner.

Ingere `reference/governadores.xlsx` (nome, UF, partido, link do perfil) como
tabela de dimensão no Delta Lake, para servir de fonte única de verdade para
o dashboard (nome/UF/partido) em vez de ler a planilha bruta a cada carregamento.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pandas as pd

from src.delta_io import write_delta
from src.schemas_delta import SILVER_GOVERNORS_METADATA_SCHEMA


class GovernorsMetadataCleaner:
    COLUMN_MAP: ClassVar[dict[str, str]] = {
        "Governador": "nome",
        "Unidade Federativa": "uf",
        "Partido": "partido",
        "Link": "inputUrl",
    }

    def clean(self, df_raw: pd.DataFrame, run_id: str) -> pd.DataFrame:
        df = df_raw.copy()
        df.columns = df.columns.str.strip()

        missing = [c for c in self.COLUMN_MAP if c not in df.columns]
        if missing:
            raise ValueError(
                f"Colunas esperadas ausentes em governadores.xlsx: {missing}"
            )

        df = df[list(self.COLUMN_MAP)].rename(columns=self.COLUMN_MAP)
        for col in ("nome", "uf", "partido", "inputUrl"):
            df[col] = df[col].astype(str).str.strip()

        # A planilha é mantida manualmente e pode repetir uma linha (edição
        # duplicada, cópia de outro ano) -- mantém só a primeira ocorrência.
        df = df.drop_duplicates(subset=["inputUrl"], keep="first")

        df["_ingested_at"] = pd.Timestamp.now(tz="UTC")
        df["_run_id"] = run_id
        df["_source_layer"] = "raw_xlsx"

        return df

    def write(self, df_silver: pd.DataFrame, path: Path | str) -> None:
        write_delta(path, df_silver, SILVER_GOVERNORS_METADATA_SCHEMA)
