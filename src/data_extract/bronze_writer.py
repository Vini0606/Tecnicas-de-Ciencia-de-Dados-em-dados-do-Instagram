"""
src/data_extract/bronze_writer.py
BronzeWriter implementation using deltalake write_deltalake.
"""

from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
from deltalake import DeltaTable

from src.delta_io import write_delta
from src.schemas_delta import (
    BRONZE_POSTS_SCHEMA,
    BRONZE_PROFILES_SCHEMA,
    BRONZE_REELS_SCHEMA,
    BRONZE_UGC_MENTIONS_SCHEMA,
)


def _escalar_para_texto(value: bool | float) -> str | None:
    """Float com parte inteira exata (ex.: id `333.0`) vira `"333"`, não
    `"333.0"`; NaN vira nulo."""
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if value.is_integer():
            return str(int(value))
    return str(value)


class BronzeWriter:
    def __init__(
        self,
        bronze_profiles_path: Path | str,
        bronze_posts_path: Path | str,
        bronze_reels_path: Path | str,
        storage_options: dict | None = None,
        # ADR 0020 (Ficha 8) / issue #93: opcional e por último, por
        # compatibilidade. Desde a issue #211 todo chamador de
        # `extract_and_land` passa este caminho (UGC é parte da extração);
        # ausente, write_ugc_mentions levanta KeyError explícito -- que
        # `extract_and_land` trata como "coleta de UGC pulada".
        bronze_ugc_mentions_path: Path | str | None = None,
    ):
        self._paths = {
            "profiles": str(bronze_profiles_path),
            "posts": str(bronze_posts_path),
            "reels": str(bronze_reels_path),
        }
        if bronze_ugc_mentions_path is not None:
            self._paths["ugc_mentions"] = str(bronze_ugc_mentions_path)
        self._storage_options = storage_options or {}

    def write_profiles(self, raw_data: list[dict], run_id: str | None = None) -> str:
        return self._write(
            raw_data, self._paths["profiles"], BRONZE_PROFILES_SCHEMA, run_id
        )

    def write_posts(self, raw_data: list[dict], run_id: str | None = None) -> str:
        return self._write(raw_data, self._paths["posts"], BRONZE_POSTS_SCHEMA, run_id)

    def write_reels(self, raw_data: list[dict], run_id: str | None = None) -> str:
        return self._write(raw_data, self._paths["reels"], BRONZE_REELS_SCHEMA, run_id)

    def write_ugc_mentions(self, raw_data: list[dict], run_id: str | None = None) -> str:
        return self._write(
            raw_data, self._paths["ugc_mentions"], BRONZE_UGC_MENTIONS_SCHEMA, run_id
        )

    def get_latest_profiles(self) -> pd.DataFrame:
        return self._read_latest(self._paths["profiles"])

    def get_profiles_at(
        self, version: int | None = None, timestamp: str | None = None
    ) -> pd.DataFrame:
        return self._read_at(
            self._paths["profiles"], version=version, timestamp=timestamp
        )

    def get_latest_posts(self) -> pd.DataFrame:
        return self._read_latest(self._paths["posts"])

    def get_latest_reels(self) -> pd.DataFrame:
        return self._read_latest(self._paths["reels"])

    def get_latest_ugc_mentions(self) -> pd.DataFrame:
        return self._read_latest(self._paths["ugc_mentions"])

    def get_history(self, entity: str) -> pd.DataFrame:
        dt = DeltaTable(self._paths[entity], storage_options=self._storage_options)
        return pd.DataFrame(dt.history())

    def _add_ingestion_metadata(
        self, raw_data: list[dict], run_id: str, schema: pa.Schema | None = None
    ) -> list[dict]:
        now_utc = datetime.now(timezone.utc)
        # Issue #229: a Apify não é consistente no tipo de campos escalares
        # (ex.: `ownerId` veio int em 2 de 522 reels reais) -- em campo que o
        # schema Bronze declara string, int/float/bool viram texto antes da
        # conformação, em vez de abortar a extração inteira já paga.
        campos_texto = (
            {f.name for f in schema if pa.types.is_string(f.type)} if schema is not None else set()
        )
        enriched = []
        for record in raw_data:
            enriched_record = dict(record)
            # ADR 0039: a Bronze é fiel -- o item completo da Apify vai
            # inteiro numa coluna, mesmo os campos que o schema não modela.
            raw_item = json.dumps(record, ensure_ascii=False, default=str)
            for key, value in list(enriched_record.items()):
                if isinstance(value, (list, dict)):
                    enriched_record[key] = json.dumps(value, ensure_ascii=False)
                elif key in campos_texto and isinstance(value, (bool, int, float)):
                    enriched_record[key] = _escalar_para_texto(value)
            enriched_record["_ingested_at"] = now_utc
            enriched_record["_run_id"] = run_id
            enriched_record["_source"] = "apify"
            enriched_record["_raw"] = raw_item
            enriched.append(enriched_record)
        return enriched

    def _write(
        self, raw_data: list[dict], path: str, schema: pa.Schema, run_id: str | None
    ) -> str:
        if not raw_data:
            raise ValueError(f"Nenhum dado fornecido para escrita em Bronze: {path}")

        run_id = run_id or str(uuid.uuid4())
        enriched = self._add_ingestion_metadata(raw_data, run_id, schema)
        df = pd.DataFrame(enriched)

        write_delta(
            path,
            df,
            schema,
            mode="overwrite",
            storage_options=self._storage_options,
        )

        return run_id

    def _read_latest(self, path: str) -> pd.DataFrame:
        try:
            dt = DeltaTable(path, storage_options=self._storage_options)
            return dt.to_pandas()
        except Exception as e:
            raise FileNotFoundError(
                f"Tabela Bronze não encontrada em {path}. Execute o pipeline de extração primeiro. Detalhe: {e}"
            ) from e

    def _read_at(
        self, path: str, version: int | None, timestamp: str | None
    ) -> pd.DataFrame:
        dt = DeltaTable(path, storage_options=self._storage_options)
        if version is not None:
            return dt.load_as_version(version).to_pandas()
        if timestamp is not None:
            return dt.load_with_datetime(timestamp).to_pandas()
        raise ValueError("Forneça version ou timestamp para time travel.")
