"""
Parsing e validacao explicitos do dado bruto da Bronze fiel (ADR 0039).

A Bronze guarda o item como a Apify entregou e existe uma Coleta vigente so:
nao ha varias versoes do mesmo registro para escolher. Erros de formato
(timestamp ilegivel, numero que nao e numero, JSON invalido, id repetido)
nunca somem em silencio -- viram rejeicao ou valor padrao COM log de warning.
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def drop_duplicate_ids(df: pd.DataFrame, id_col: str, entity: str) -> pd.DataFrame:
    """Dentro da Coleta vigente um `id` deve aparecer uma vez. Repeticao
    (ex.: Recortes sobrepostos) mantem a primeira linha, com warning."""
    if id_col not in df.columns:
        return df
    repetidos = df.duplicated(subset=[id_col], keep="first")
    if repetidos.any():
        logger.warning(
            "Descartando %d %s(s) com `%s` repetido na Coleta (mantida a primeira "
            "ocorrencia): %s",
            int(repetidos.sum()),
            entity,
            id_col,
            df.loc[repetidos, id_col].astype(str).unique().tolist()[:10],
        )
    return df[~repetidos]


def parse_timestamp_sp(series: pd.Series, entity: str) -> pd.Series:
    """ISO 8601 -> horario de Sao Paulo sem timezone. Valor presente mas
    ilegivel vira NaT com warning (o chamador decide se rejeita a linha)."""
    parsed = pd.to_datetime(series, errors="coerce", utc=True, format="ISO8601")
    invalidos = parsed.isna() & series.notna()
    if invalidos.any():
        logger.warning(
            "%d %s(s) com `timestamp` fora do formato ISO 8601: %s",
            int(invalidos.sum()),
            entity,
            series[invalidos].astype(str).unique().tolist()[:10],
        )
    return parsed.dt.tz_convert("America/Sao_Paulo").dt.tz_localize(None)


def drop_invalid_timestamp(df: pd.DataFrame, entity: str) -> pd.DataFrame:
    """Rejeita (com warning) linhas cujo `data_hora` ficou nulo: a coluna e
    NOT NULL no contrato Silver e uma linha assim derrubaria a escrita."""
    if "data_hora" not in df.columns:
        return df
    sem_data = df["data_hora"].isna()
    if sem_data.any():
        logger.warning(
            "Rejeitando %d %s(s) sem `timestamp` valido (data_hora e obrigatoria na Silver)",
            int(sem_data.sum()),
            entity,
        )
    return df[~sem_data]


def to_numeric_logged(series: pd.Series, col: str, entity: str) -> pd.Series:
    """`pd.to_numeric` que registra warning para valores presentes mas nao
    numericos (viram NaN; o chamador decide o padrao)."""
    num = pd.to_numeric(series, errors="coerce")
    invalidos = num.isna() & series.notna()
    if invalidos.any():
        logger.warning(
            "%d %s(s) com `%s` nao numerico: %s",
            int(invalidos.sum()),
            entity,
            col,
            series[invalidos].astype(str).unique().tolist()[:10],
        )
    return num
