"""Funções puras reaproveitadas pelos notebooks de diagnóstico Medallion
(`notebooks/diagnostico_medallion/`, issue #128 / ADR 0022). Mantido mínimo de
propósito -- só o que de fato se repete entre os notebooks, não um framework
de diagnóstico genérico."""

from __future__ import annotations

import pandas as pd


def completeness_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Resumo de completude por coluna: nulos, percentual de nulos e valores
    únicos não-nulos. Uma linha por coluna, na ordem original de `df`."""
    n_linhas = len(df)
    linhas = []
    for coluna in df.columns:
        serie = df[coluna]
        n_nulos = int(serie.isna().sum())
        linhas.append(
            {
                "coluna": coluna,
                "dtype": str(serie.dtype),
                "n_nulos": n_nulos,
                "pct_nulos": (n_nulos / n_linhas * 100) if n_linhas else 0.0,
                "n_unicos": int(serie.nunique(dropna=True)),
            }
        )
    return pd.DataFrame(linhas)


def count_duplicate_rows(df: pd.DataFrame, subset: list[str] | None = None) -> int:
    """Conta linhas duplicadas -- por padrão considerando todas as colunas;
    `subset` restringe a checagem a um subconjunto delas."""
    return int(df.duplicated(subset=subset).sum())


def with_governor_metadata(
    df: pd.DataFrame,
    df_governors_metadata: pd.DataFrame,
    how: str = "left",
) -> pd.DataFrame:
    """Junta `df` (uma tabela Gold/Silver qualquer) com `governors_metadata`
    por `inputUrl`, trazendo `nome`/`uf`/`partido` para quebras por
    covariável. `how="left"` por padrão preserva todas as linhas de `df`
    mesmo sem metadado correspondente (perfil sem match vira NaN nas colunas
    de metadado, não é descartado)."""
    if "inputUrl" not in df.columns:
        raise ValueError("`df` precisa ter a coluna 'inputUrl' para o join com governors_metadata.")
    if "inputUrl" not in df_governors_metadata.columns:
        raise ValueError(
            "`df_governors_metadata` precisa ter a coluna 'inputUrl' para o join."
        )
    return df.merge(df_governors_metadata, on="inputUrl", how=how, suffixes=("", "_metadata"))
