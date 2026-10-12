"""Filtro de período das métricas de publicações (ADR 0041 / issue #281).

Funções puras (DataFrame in, DataFrame out), sem Streamlit -- o componente
visual vive em `dashboard/core/seletor_periodo.py`. Reaproveitam
`filter_by_date_range` de `deltas.py` (ADR 0023) em vez de reimplementar o
corte por intervalo.

Regra de fixados: uma publicação fixada no perfil pode ter data bem anterior
à janela da extração e distorce o período; fica fora das métricas de
publicações. Valor nulo ou coluna ausente = NÃO fixado (a Bronze de posts de
feed antiga não trazia o campo; excluir o nulo apagaria posts legítimos).
"""

from __future__ import annotations

import datetime
import re

import pandas as pd

from dashboard.core.deltas import filter_by_date_range

COLUNA_FIXADO = "isPinned"
_COL_DATA_TEMP = "_data_publicacao"


def _eh_fixado(serie: pd.Series) -> pd.Series:
    """True só onde o valor é verdadeiro; nulo/NaN/qualquer outra coisa = False."""
    return serie.map(lambda v: False if pd.isna(v) else bool(v)).astype(bool)


def excluir_fixados(df: pd.DataFrame, coluna: str = COLUNA_FIXADO) -> pd.DataFrame:
    """Remove as publicações fixadas. Nulo e coluna ausente contam como não fixado."""
    if df.empty or coluna not in df.columns:
        return df
    return df[~_eh_fixado(df[coluna])].reset_index(drop=True)


MENSAGEM_FIXADOS_INDISPONIVEL = (
    "Marcação de publicações fixadas indisponível nesta Coleta; filtro de fixados inativo."
)


def marcacao_fixados_indisponivel(*dfs: pd.DataFrame, coluna: str = COLUNA_FIXADO) -> bool:
    """True se algum DataFrame não vazio não traz a coluna de fixado (Silver ainda
    não reconstruída, ADR 0041) -- o filtro de fixados fica inerte e a tela avisa."""
    return any(not df.empty and coluna not in df.columns for df in dfs)


def _datas(df: pd.DataFrame, date_col: str) -> pd.Series:
    """Converte `date_col` (datetime da Silver) em dia. Não reaproveita
    `deltas.parse_publication_dates`: aquela lê string ISO 8601 e força UTC, o que
    pode deslocar o dia de um datetime com fuso; aqui o dia é o da própria coluna."""
    return pd.to_datetime(df[date_col], errors="coerce").dt.date


def limites_de_datas(
    df: pd.DataFrame, date_col: str, sem_fixados: bool = True
) -> tuple[datetime.date, datetime.date] | None:
    """Menor e maior dia com publicação (fixadas fora). None se não há dado."""
    if df.empty or date_col not in df.columns:
        return None
    base = excluir_fixados(df) if sem_fixados else df
    datas = _datas(base, date_col).dropna()
    if datas.empty:
        return None
    return datas.min(), datas.max()


def filtrar_publicacoes(
    df: pd.DataFrame,
    date_col: str,
    data_inicio: object | None,
    data_fim: object | None,
    sem_fixados: bool = True,
) -> pd.DataFrame:
    """Período (inclusive nas duas pontas, por dia) + exclusão de fixados.

    `None` num lado não corta aquele lado. Período sem publicações devolve um
    DataFrame vazio com as mesmas colunas, nunca lança exceção.
    """
    if df.empty or date_col not in df.columns:
        return df
    base = excluir_fixados(df) if sem_fixados else df
    com_data = base.assign(**{_COL_DATA_TEMP: _datas(base, date_col)})
    if data_inicio is not None or data_fim is not None:
        com_data = com_data.dropna(subset=[_COL_DATA_TEMP])
    filtrado = filter_by_date_range(com_data, _COL_DATA_TEMP, data_inicio, data_fim)
    return filtrado.drop(columns=[_COL_DATA_TEMP]).reset_index(drop=True)


def ajustar_intervalo(
    data_inicio: datetime.date,
    data_fim: datetime.date,
    limites: tuple[datetime.date, datetime.date],
) -> tuple[datetime.date, datetime.date]:
    """Reordena um intervalo invertido e o prende a `limites` (menor/maior dia
    com dado). Intervalo todo fora dos limites colapsa na borda mais próxima."""
    minimo, maximo = limites
    inicio, fim = sorted((data_inicio, data_fim))
    inicio = min(max(inicio, minimo), maximo)
    fim = min(max(fim, minimo), maximo)
    return inicio, fim


_PADRAO_DATA = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}")


def _parse_data(texto: str) -> datetime.date | None:
    try:
        if "/" in texto:
            dia, mes, ano = (int(x) for x in texto.split("/"))
            return datetime.date(ano, mes, dia)
        return datetime.date.fromisoformat(texto)
    except ValueError:
        return None


def parse_intervalo_digitado(texto: str) -> tuple[datetime.date, datetime.date] | None:
    """Lê "de DD/MM/AAAA até DD/MM/AAAA" (ou AAAA-MM-DD; "ate" sem acento; uma
    data só = dia único). None se não houver 1 ou 2 datas válidas."""
    achadas = _PADRAO_DATA.findall(texto or "")
    if not 1 <= len(achadas) <= 2:
        return None
    datas = [_parse_data(a) for a in achadas]
    if any(d is None for d in datas):
        return None
    return datas[0], datas[-1]
