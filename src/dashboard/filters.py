"""
Filtros de grupo (região/partido/cluster) e seletor individual de governador,
compartilhados entre as páginas `exploratory` e `modeling` via `st.session_state`
(através das `key=` dos widgets abaixo).

Decisões de design (sessão de grilling de 2026-08-29, ver handoff):
- Região/partido/nome vêm de `governors_metadata` (Silver, ingerida de
  `governadores.xlsx`) -- se a tabela ainda não existir (pipeline não rodado
  após esta mudança), tudo aqui degrada graciosamente: filtros ficam sem
  opções e o seletor individual cai para URLs brutas, em vez de quebrar a página.
- O filtro de cluster é por "contém" (pelo menos 1 reel no cluster
  selecionado), não por "cluster dominante" (moda) -- outliers do DBSCAN
  (cluster -1) podem ser reels virais/atípicos, e a moda esconderia esse sinal
  num governador que só tem 1-2 reels fora do padrão.
- É um dado de clustering *por reel*, não por perfil -- rotulado como tal na
  UI. Clustering por perfil é uma frente futura separada (Fase 2).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.dashboard.loaders import load_clusters, load_governors_metadata, load_reels


def _normalize_url(series: pd.Series) -> pd.Series:
    """Normaliza URL de perfil para join: remove espaços, query string/fragmento
    (ex: `?hl=en`), barra final e caixa -- `inputUrl` nos dados raspados é uma
    cópia literal do `Link` do xlsx e hoje carrega o mesmo `?hl=en` quando
    presente, mas a normalização não deve depender dessa coincidência."""
    return (
        series.astype(str)
        .str.strip()
        .str.split("?", n=1).str[0]
        .str.split("#", n=1).str[0]
        .str.rstrip("/")
        .str.lower()
    )


@st.cache_data
def build_governor_directory() -> pd.DataFrame:
    """Diretório com 1 linha por governador: inputUrl, nome, uf, partido.

    DataFrame vazio (mas com essas colunas) se `governors_metadata` ainda não
    existir -- chamadores devem tratar isso como "pipeline não rodado ainda",
    não como erro.
    """
    df_meta = load_governors_metadata()
    if df_meta.empty:
        return pd.DataFrame(columns=["inputUrl", "nome", "uf", "partido"])
    return df_meta[["inputUrl", "nome", "uf", "partido"]].copy()


@st.cache_data
def build_cluster_membership() -> pd.DataFrame:
    """Uma linha por (inputUrl, cluster_label) -- quais clusters de reel cada
    governador tem pelo menos 1 reel. Base do filtro "contém cluster X"."""
    df_reels = load_reels()
    df_clusters = load_clusters()
    if df_reels.empty or df_clusters.empty:
        return pd.DataFrame(columns=["inputUrl", "cluster_label"])
    merged = df_reels.merge(df_clusters, left_on="id", right_on="id_reel", how="inner")
    return merged[["inputUrl", "cluster_label"]].drop_duplicates()


def enrich_with_governor_metadata(df: pd.DataFrame, url_col: str = "inputUrl") -> pd.DataFrame:
    """Adiciona nome/uf/partido a `df` via join por `url_col` (normalizado:
    strip + sem barra final + minúsculo, já que `governadores.xlsx` tem
    espaços em branco ao redor dos links). Preserva todas as linhas de `df`
    (left join); linhas sem match ficam com nome/uf/partido nulos e geram um
    aviso visível (dado sujo é melhor sinalizado que escondido)."""
    directory = build_governor_directory()
    df = df.copy()
    if url_col not in df.columns or directory.empty:
        for col in ("nome", "uf", "partido"):
            if col not in df.columns:
                df[col] = pd.NA
        return df

    df["_match_key"] = _normalize_url(df[url_col])
    directory = directory.copy()
    directory["_match_key"] = _normalize_url(directory["inputUrl"])

    merged = df.merge(
        directory[["_match_key", "nome", "uf", "partido"]],
        on="_match_key",
        how="left",
    ).drop(columns="_match_key")

    unmatched = merged.loc[merged["nome"].isna(), url_col].dropna().unique().tolist()
    if unmatched:
        st.warning(
            "Não foi possível casar estes perfis com `governadores.xlsx` "
            f"(nome/UF/partido ficarão vazios): {', '.join(unmatched)}"
        )
    return merged


def render_group_filters(directory: pd.DataFrame, cluster_membership: pd.DataFrame) -> dict:
    """Renderiza os filtros de grupo (região, partido, cluster) na sidebar.
    Compartilhados entre páginas via `key=` -- a seleção persiste ao navegar."""
    st.sidebar.header("Filtros de Grupo")

    uf_options = sorted(directory["uf"].dropna().unique().tolist())
    partido_options = sorted(directory["partido"].dropna().unique().tolist())
    cluster_options = sorted(cluster_membership["cluster_label"].dropna().unique().tolist())

    selected_uf = st.sidebar.multiselect(
        "Região (UF):", options=uf_options, key="filter_uf"
    )
    selected_partido = st.sidebar.multiselect(
        "Partido:", options=partido_options, key="filter_partido"
    )
    selected_cluster = st.sidebar.multiselect(
        "Cluster de Reels (dado atual, por reel):",
        options=cluster_options,
        key="filter_cluster",
        help=(
            "Mostra governadores com pelo menos um reel no(s) cluster(s) "
            "selecionado(s). `-1` é o rótulo de ruído/outlier do DBSCAN -- "
            "pode ser reel viral ou de audiência atípica, não é 'lixo'. "
            "Este clustering é por reel, não por perfil de governador."
        ),
    )

    if not uf_options and not partido_options and not cluster_options:
        st.sidebar.caption(
            "Sem dados de região/partido/cluster ainda -- rode a pipeline "
            "(`uv run python pipeline.py`) para popular os filtros de grupo."
        )

    return {"uf": selected_uf, "partido": selected_partido, "cluster": selected_cluster}


def apply_group_filters(
    df_enriched: pd.DataFrame,
    filters: dict,
    cluster_membership: pd.DataFrame,
    url_col: str = "inputUrl",
) -> pd.DataFrame:
    """Aplica os filtros de `render_group_filters` sobre um DataFrame que já
    tenha as colunas `uf`/`partido`/`url_col` (ex: via `enrich_with_governor_metadata`
    ou `build_governor_directory`). Seleção vazia em um filtro = não filtra por ele.

    O casamento do filtro de cluster usa `inputUrl` normalizado (não `==` direto):
    `governor_engagement` grava a URL com barra final, mas `reels_clean` e
    `governor_sentiment` gravam sem -- comparar sem normalizar faz o filtro de
    cluster nunca casar nada em `exploratory`."""
    df = df_enriched
    if filters["uf"]:
        df = df[df["uf"].isin(filters["uf"])]
    if filters["partido"]:
        df = df[df["partido"].isin(filters["partido"])]
    if filters["cluster"]:
        cm = cluster_membership.copy()
        cm["_match_key"] = _normalize_url(cm["inputUrl"])
        keys_in_clusters = set(
            cm.loc[cm["cluster_label"].isin(filters["cluster"]), "_match_key"]
        )
        df = df.copy()
        df["_match_key"] = _normalize_url(df[url_col])
        df = df[df["_match_key"].isin(keys_in_clusters)].drop(columns="_match_key")
    return df


def render_governor_selector(
    directory_filtered: pd.DataFrame,
    directory_exists: bool,
    fallback_urls: list[str] | None = None,
) -> str | None:
    """Seletor individual de governador (por nome), exclusivo de `modeling`,
    em cascata com os filtros de grupo (`directory_filtered` já vem filtrado).

    Se `governors_metadata` ainda não existir, cai para uma lista de URLs
    brutas (`fallback_urls`, tipicamente `df_comments["inputUrl"].unique()`)
    em vez de quebrar a página -- comportamento idêntico ao seletor anterior."""
    if directory_exists:
        if directory_filtered.empty:
            st.sidebar.warning(
                "Nenhum governador corresponde aos filtros de grupo selecionados."
            )
            return None
        options = directory_filtered["inputUrl"].dropna().unique().tolist()
        label_by_url = dict(
            zip(
                directory_filtered["inputUrl"],
                directory_filtered["nome"].fillna(directory_filtered["inputUrl"]),
            )
        )
        format_func = lambda url: label_by_url.get(url, url)  # noqa: E731
    elif fallback_urls:
        st.sidebar.info(
            "Tabela `governors_metadata` ainda não existe -- mostrando por "
            "URL do perfil. Rode a pipeline para ver nomes."
        )
        options = fallback_urls
        format_func = lambda url: url  # noqa: E731
    else:
        st.sidebar.warning("Nenhum governador disponível.")
        return None

    return st.sidebar.selectbox(
        "Selecione o Governador:", options=options, format_func=format_func
    )
