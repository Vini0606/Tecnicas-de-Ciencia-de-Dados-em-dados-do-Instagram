"""Utilitarios compartilhados pelo contêiner do Resumo e pelas sub-abas
(NSM, Funil, Scorecard) -- ADR 0031 / issue #183.

Vive num módulo próprio para que as sub-abas possam importar sem ciclo com
`resumo.py` (que as registra). Funções puras, sem I/O de Streamlit.
"""

from __future__ import annotations

import pandas as pd

_PLACEHOLDER_SEM_GOVERNADOR = "—"

# ADR 0027 / issue #161: sentinela de "Todos os Governadores" no seletor --
# nunca uma URL real, tratado à parte em cada ponto de agregação abaixo.
# Não confundir com uma URL ausente (`governor_url is None`, "sem
# governador disponível ainda"): esta é uma seleção explícita e válida.
TODOS_OS_GOVERNADORES = "__todos_os_governadores__"
_LABEL_TODOS_OS_GOVERNADORES = "Todos os Governadores"


# ---------------------------------------------------------------------------
# Normalização / seleção de governador
# ---------------------------------------------------------------------------


def _normalize_url(series: pd.Series) -> pd.Series:
    """Normaliza URL de perfil para join (remove espaço, query string,
    fragmento, barra final, caixa) -- mesma normalização que
    `src/dashboard/filters.py::_normalize_url` já precisou aplicar
    historicamente porque `governor_engagement`/`governor_sentiment`/
    `reels_clean` nem sempre gravam a mesma URL byte-a-byte igual. Duplicada
    aqui (função pequena, sem estado) em vez de importada de
    `src/dashboard/filters.py`, que está sendo descontinuado tela por tela
    pela ADR 0021 -- Tela 1 não deve criar uma nova dependência num módulo
    que vai desaparecer."""
    return (
        series.astype(str)
        .str.strip()
        .str.split("?", n=1)
        .str[0]
        .str.split("#", n=1)
        .str[0]
        .str.rstrip("/")
        .str.lower()
    )


def _governor_options(df_metadata: pd.DataFrame) -> dict[str, str]:
    """`{nome_de_exibição: inputUrl}`, ordenado por nome -- opções do
    `st.selectbox` de governador. Vazio (não lança exceção) se
    `governors_metadata` ainda não existir; `render()` degrada para as URLs
    brutas de `load_engagement()` nesse caso (ver `render()` abaixo)."""
    if df_metadata.empty or "inputUrl" not in df_metadata.columns:
        return {}
    col_nome = "nome" if "nome" in df_metadata.columns else "inputUrl"
    pares = (
        df_metadata[["inputUrl", col_nome]]
        .dropna(subset=["inputUrl"])
        .drop_duplicates(subset=["inputUrl"])
    )
    nomes = pares[col_nome].fillna(pares["inputUrl"])
    return dict(
        sorted(zip(nomes, pares["inputUrl"], strict=True), key=lambda kv: kv[0])
    )


def _filtrar_por_governador(
    df: pd.DataFrame, governor_url: str, url_col: str = "inputUrl"
) -> pd.DataFrame:
    """`df` filtrado às linhas cujo `url_col` normalizado bate com
    `governor_url` normalizado. `DataFrame` vazio (nunca exceção) se `df`
    estiver vazio ou não tiver `url_col`."""
    if df.empty or url_col not in df.columns:
        return df.iloc[0:0]
    chave = _normalize_url(pd.Series([governor_url])).iloc[0]
    return df[_normalize_url(df[url_col]) == chave]


def _filtrar_por_governador_ou_todos(
    df: pd.DataFrame, governor_url: str, url_col: str = "inputUrl"
) -> pd.DataFrame:
    """`df` INTEIRO (sem filtro) quando `governor_url == TODOS_OS_GOVERNADORES`
    (ADR 0027 / issue #161) -- senão delega a `_filtrar_por_governador`.

    Uso restrito de propósito: só onde "todos os governadores juntos, sem
    distinguir" já é a semântica correta por construção -- hoje só o
    conteúdo do gráfico de evidência (`_conteudo_do_governador_por_tipo`),
    que soma/conta por dia sobre todas as linhas recebidas de qualquer
    forma. NUNCA usar nos pontos que fazem `.iloc[0]` esperando exatamente 1
    linha de snapshot por governador (KPIs de perfil/crescimento) -- esses
    têm seu próprio caminho de agregação explícito (soma ou média simples
    entre governadores) em `render()`, para não silenciosamente pegar só o
    1º governador da lista quando "Todos" está selecionado."""
    if governor_url == TODOS_OS_GOVERNADORES:
        return df
    return _filtrar_por_governador(df, governor_url, url_col)
