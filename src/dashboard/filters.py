"""
Filtros de grupo (região/partido/cluster) e seletor individual de governador,
compartilhados entre as páginas `exploratory` e `modeling` via `st.session_state`
(através das `key=` dos widgets abaixo).

Decisões de design (sessão de grilling de 2026-08-29, ver handoff):
- Região/partido/nome vêm de `governors_metadata` (Silver, ingerida de
  `governadores.xlsx`) -- se a tabela ainda não existir (pipeline não rodado
  após esta mudança), tudo aqui degrada graciosamente: filtros ficam sem
  opções e o seletor individual cai para URLs brutas, em vez de quebrar a página.
- "Região" filtra pela macrorregião (Norte/Nordeste/Centro-Oeste/Sudeste/Sul),
  não pela UF -- há sempre exatamente 1 governador por UF, então um filtro por
  UF nunca agrupa nada, só reimplementa o seletor individual de forma mais lenta.
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

TODOS_GOVERNADORES = "__todos_governadores__"

UF_PARA_REGIAO: dict[str, str] = {
    "Acre": "Norte",
    "Amapá": "Norte",
    "Amazonas": "Norte",
    "Pará": "Norte",
    "Rondônia": "Norte",
    "Roraima": "Norte",
    "Tocantins": "Norte",
    "Alagoas": "Nordeste",
    "Bahia": "Nordeste",
    "Ceará": "Nordeste",
    "Maranhão": "Nordeste",
    "Paraíba": "Nordeste",
    "Pernambuco": "Nordeste",
    "Piauí": "Nordeste",
    "Rio Grande do Norte": "Nordeste",
    "Sergipe": "Nordeste",
    "Distrito Federal": "Centro-Oeste",
    "Goiás": "Centro-Oeste",
    "Mato Grosso": "Centro-Oeste",
    "Mato Grosso do Sul": "Centro-Oeste",
    "Espírito Santo": "Sudeste",
    "Minas Gerais": "Sudeste",
    "Rio de Janeiro": "Sudeste",
    "São Paulo": "Sudeste",
    "Paraná": "Sul",
    "Rio Grande do Sul": "Sul",
    "Santa Catarina": "Sul",
}


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


def _with_match_key(df: pd.DataFrame, url_col: str = "inputUrl") -> pd.DataFrame:
    """Copia `df` e adiciona `_match_key` (URL normalizada de `url_col`) --
    passo repetido em todo cruzamento de tabelas por inputUrl neste módulo,
    já que tabelas diferentes gravam a mesma URL com formatação diferente
    (`governor_engagement` com barra final, `reels_clean`/`governor_sentiment`
    sem, por exemplo)."""
    df = df.copy()
    df["_match_key"] = _normalize_url(df[url_col])
    return df


def _add_regiao(df: pd.DataFrame) -> pd.DataFrame:
    """Deriva `regiao` (macrorregião) a partir de `uf`. Nomes de UF fora do
    mapeamento (não deveria acontecer com os 27 estados atuais) viram 'Outra'
    em vez de quebrar."""
    df = df.copy()
    df["regiao"] = df["uf"].map(UF_PARA_REGIAO).fillna("Outra")
    return df


@st.cache_data
def build_governor_directory() -> pd.DataFrame:
    """Diretório com 1 linha por governador: inputUrl, nome, uf, regiao, partido.

    DataFrame vazio (mas com essas colunas) se `governors_metadata` ainda não
    existir -- chamadores devem tratar isso como "pipeline não rodado ainda",
    não como erro.
    """
    df_meta = load_governors_metadata()
    if df_meta.empty:
        return pd.DataFrame(columns=["inputUrl", "nome", "uf", "regiao", "partido"])
    directory = df_meta[["inputUrl", "nome", "uf", "partido"]].copy()
    return _add_regiao(directory)


@st.cache_data
def build_cluster_membership() -> pd.DataFrame:
    """Uma linha por (inputUrl, cluster_label) -- quais clusters de reel cada
    governador tem pelo menos 1 reel. Base do filtro "contém cluster X".

    `reels_clean` (Silver) é uma tabela "core" do pipeline (existe desde que
    o Silver tenha rodado alguma vez), mas o filtro de cluster é opcional --
    então tratamos a ausência dela aqui como "sem dado ainda", não como erro,
    para não derrubar `exploratory`/`modeling` por causa de um filtro opcional."""
    try:
        df_reels = load_reels()
    except FileNotFoundError:
        return pd.DataFrame(columns=["inputUrl", "cluster_label"])
    df_clusters = load_clusters()
    if df_reels.empty or df_clusters.empty:
        return pd.DataFrame(columns=["inputUrl", "cluster_label"])
    merged = df_reels.merge(df_clusters, left_on="id", right_on="id_reel", how="inner")
    return merged[["inputUrl", "cluster_label"]].drop_duplicates()


def enrich_with_governor_metadata(df: pd.DataFrame, url_col: str = "inputUrl") -> pd.DataFrame:
    """Adiciona nome/uf/regiao/partido a `df` via join por `url_col` (URL
    normalizada -- ver `_normalize_url`). Preserva todas as linhas de `df`
    (left join); linhas sem match ficam com essas colunas nulas.

    Função pura (sem I/O de UI) -- chame `render_unmatched_warning` depois se
    quiser avisar visivelmente sobre perfis sem match."""
    directory = build_governor_directory()
    df = df.copy()
    if url_col not in df.columns or directory.empty:
        for col in ("nome", "uf", "regiao", "partido"):
            if col not in df.columns:
                df[col] = pd.NA
        return df

    df = _with_match_key(df, url_col)
    directory = _with_match_key(directory, "inputUrl")

    merged = df.merge(
        directory[["_match_key", "nome", "uf", "regiao", "partido"]],
        on="_match_key",
        how="left",
    ).drop(columns="_match_key")
    return merged


def render_unmatched_warning(df_enriched: pd.DataFrame, url_col: str = "inputUrl") -> None:
    """Mostra um `st.warning` visível se alguma linha de `df_enriched` (já
    passado por `enrich_with_governor_metadata`) não casou com `governadores.xlsx`
    -- dado sujo é melhor sinalizado que escondido. Separado de
    `enrich_with_governor_metadata` para manter aquela função pura (só dado,
    sem I/O de UI), seguindo a convenção `render_*` = mexe em UI deste módulo."""
    if "nome" not in df_enriched.columns:
        return
    unmatched = df_enriched.loc[df_enriched["nome"].isna(), url_col].dropna().unique().tolist()
    if unmatched:
        st.warning(
            "Não foi possível casar estes perfis com `governadores.xlsx` "
            f"(nome/UF/partido ficarão vazios): {', '.join(unmatched)}"
        )


def render_group_filters(governor_directory: pd.DataFrame, cluster_membership: pd.DataFrame) -> dict:
    """Renderiza os filtros de grupo (região, partido, cluster) na sidebar.
    Compartilhados entre páginas via `key=` -- a seleção persiste ao navegar."""
    st.sidebar.header("Filtros de Grupo")

    regiao_options = sorted(governor_directory["regiao"].dropna().unique().tolist())
    partido_options = sorted(governor_directory["partido"].dropna().unique().tolist())
    cluster_options = sorted(cluster_membership["cluster_label"].dropna().unique().tolist())

    selected_regiao = st.sidebar.multiselect(
        "Região:", options=regiao_options, key="filter_regiao"
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

    if not regiao_options and not partido_options and not cluster_options:
        st.sidebar.caption(
            "Sem dados de região/partido/cluster ainda -- rode a pipeline "
            "(`uv run python pipeline.py`) para popular os filtros de grupo."
        )

    return {"regiao": selected_regiao, "partido": selected_partido, "cluster": selected_cluster}


def apply_group_filters(
    df_enriched: pd.DataFrame,
    filters: dict,
    cluster_membership: pd.DataFrame,
    url_col: str = "inputUrl",
) -> pd.DataFrame:
    """Aplica os filtros de `render_group_filters` sobre um DataFrame que já
    tenha as colunas `regiao`/`partido`/`url_col` (ex: via
    `enrich_with_governor_metadata` ou `build_governor_directory`). Seleção
    vazia em um filtro = não filtra por ele.

    O casamento do filtro de cluster usa `inputUrl` normalizado (não `==`
    direto): `governor_engagement` grava a URL com barra final, mas
    `reels_clean` e `governor_sentiment` gravam sem -- comparar sem normalizar
    faz o filtro de cluster nunca casar nada em `exploratory`."""
    df = df_enriched
    if filters["regiao"]:
        df = df[df["regiao"].isin(filters["regiao"])]
    if filters["partido"]:
        df = df[df["partido"].isin(filters["partido"])]
    if filters["cluster"]:
        cm = _with_match_key(cluster_membership, "inputUrl")
        keys_in_clusters = set(
            cm.loc[cm["cluster_label"].isin(filters["cluster"]), "_match_key"]
        )
        df = _with_match_key(df, url_col)
        df = df[df["_match_key"].isin(keys_in_clusters)].drop(columns="_match_key")
    return df


def select_governor_rows(
    df: pd.DataFrame,
    selected: str | None,
    universe_urls: list[str],
    url_col: str = "inputUrl",
) -> pd.DataFrame:
    """Filtra `df` pelo governador selecionado, usando `inputUrl` normalizado
    (não `==` direto) -- mesmo cuidado do resto do módulo, já que duas tabelas
    do mesmo pipeline (`reels_clean`/`governor_sentiment`) não têm garantia
    formal de gravar a URL byte-a-byte igual.

    `selected == TODOS_GOVERNADORES` filtra por todo `universe_urls` (o
    universo de governadores já filtrado pelos filtros de grupo ativos), em
    vez de um único governador."""
    urls = universe_urls if selected == TODOS_GOVERNADORES else [selected]
    keys = set(_normalize_url(pd.Series(urls)))
    df = _with_match_key(df, url_col)
    return df[df["_match_key"].isin(keys)].drop(columns="_match_key")


def render_governor_selector(
    directory_filtered: pd.DataFrame,
    directory_exists: bool,
    fallback_urls: list[str] | None = None,
) -> str | None:
    """Seletor individual de governador (por nome), exclusivo de `modeling`,
    em cascata com os filtros de grupo (`directory_filtered` já vem filtrado).
    Sempre oferece "Todos os Governadores" (`TODOS_GOVERNADORES`) como primeira
    opção, além dos governadores individuais.

    Se `governors_metadata` ainda não existir, cai para uma lista de URLs
    brutas (`fallback_urls`, tipicamente `df_comments["inputUrl"].unique()`)
    em vez de quebrar a página -- comportamento idêntico ao seletor anterior.

    Retorna `None` só quando não há nenhum governador disponível (filtro de
    grupo restritivo demais, ou nenhum dado carregado) -- chamadores devem
    tratar `None` como "pare a página", e `TODOS_GOVERNADORES` como um valor
    de seleção válido, não como ausência de seleção."""
    if directory_exists:
        if directory_filtered.empty:
            st.sidebar.warning(
                "Nenhum governador corresponde aos filtros de grupo selecionados."
            )
            return None
        label_by_url = dict(
            zip(
                directory_filtered["inputUrl"],
                directory_filtered["nome"].fillna(directory_filtered["inputUrl"]),
            )
        )
        label_by_url[TODOS_GOVERNADORES] = "Todos os Governadores"
        options = [TODOS_GOVERNADORES] + directory_filtered["inputUrl"].dropna().unique().tolist()

        def format_func(url: str) -> str:
            return label_by_url.get(url, url)

    elif fallback_urls:
        st.sidebar.info(
            "Tabela `governors_metadata` ainda não existe -- mostrando por "
            "URL do perfil. Rode a pipeline para ver nomes."
        )
        label_by_url = {TODOS_GOVERNADORES: "Todos os Governadores"}
        options = [TODOS_GOVERNADORES] + fallback_urls

        def format_func(url: str) -> str:
            return label_by_url.get(url, url)

    else:
        st.sidebar.warning("Nenhum governador disponível.")
        return None

    return st.sidebar.selectbox(
        "Selecione o Governador:", options=options, format_func=format_func
    )
