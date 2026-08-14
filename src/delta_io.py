"""
Escrita em Delta Lake com validação de contrato de schema.

A partir do `deltalake` 1.0 o argumento `schema=` foi removido de
`write_deltalake()`. A conformação passa a ser feita antes da escrita,
convertendo o DataFrame em `pyarrow.Table` com o schema desejado — que é
onde o contrato declarado em `src/schemas_delta.py` é de fato validado.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
from deltalake import write_deltalake


def conform_to_schema(df: pd.DataFrame, schema: pa.Schema) -> pa.Table:
    """
    Converte o DataFrame para uma `pyarrow.Table` no schema informado.

    Colunas declaradas no schema e ausentes no DataFrame são criadas como
    nulas — o que faz a conversão falhar quando o campo é `nullable=False`,
    exatamente o comportamento fail-fast pretendido pelos contratos.
    Colunas presentes no DataFrame e ausentes do schema são descartadas.
    """
    df_conformed = df.copy()
    for field in schema:
        if field.name not in df_conformed.columns:
            df_conformed[field.name] = pd.NA
    return pa.Table.from_pandas(df_conformed, schema=schema, preserve_index=False)


def write_delta(
    path: Path | str,
    df: pd.DataFrame,
    schema: pa.Schema,
    mode: str = "overwrite",
    storage_options: dict | None = None,
) -> None:
    """Conforma o DataFrame ao schema e grava a tabela Delta."""
    table = conform_to_schema(df, schema)
    write_deltalake(
        str(path),
        table,
        mode=mode,
        schema_mode="overwrite" if mode == "overwrite" else "merge",
        storage_options=storage_options or {},
    )
