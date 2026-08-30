from __future__ import annotations

import os
import sys

import pandas as pd
import streamlit as st

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.dashboard.filters import (
    TODOS_GOVERNADORES,
    apply_group_filters,
    build_cluster_membership,
    build_governor_directory,
    build_profile_cluster_directory,
    enrich_with_governor_metadata,
    enrich_with_profile_cluster,
    render_governor_selector,
    render_group_filters,
    render_unmatched_warning,
    select_governor_rows,
)
from src.dashboard.loaders import load_clusters, load_comments, load_reels
from src.visualization.charts import plot_top_n_bar, plot_value_counts

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Instagram Analytics — Modelagem",
    page_icon="📈",
    layout="wide",
)


df_comments, df_reels, df_clusters = load_comments(), load_reels(), load_clusters()
tem_modelagem = "sentiment_label" in df_comments.columns

# --- BARRA LATERAL (SIDEBAR) PARA FILTROS ---
st.sidebar.header("Filtros do Dashboard")

governor_directory = build_governor_directory()
cluster_membership = build_cluster_membership()
profile_cluster_directory = build_profile_cluster_directory()
filters = render_group_filters(governor_directory, cluster_membership, profile_cluster_directory)

# O universo de opções do seletor vem do próprio inputUrl de df_comments (não
# do xlsx) -- governor_sentiment/reels_clean gravam a URL sem barra final,
# governors_metadata (xlsx) grava com barra final; usar o valor do xlsx aqui
# faria `select_governor_rows` abaixo nunca encontrar nada. nome/uf/regiao/
# partido/cluster_perfil_engajamento continuam vindo do xlsx/Gold, só que via
# join normalizado.
governor_universe = df_comments[["inputUrl"]].dropna().drop_duplicates()
governor_universe_enriched = enrich_with_governor_metadata(governor_universe)
governor_universe_enriched = enrich_with_profile_cluster(governor_universe_enriched)
render_unmatched_warning(governor_universe_enriched)
governor_universe_filtrado = apply_group_filters(
    governor_universe_enriched, filters, cluster_membership
)

st.sidebar.markdown("---")
governador_selecionado = render_governor_selector(
    governor_universe_filtrado,
    directory_exists=not governor_directory.empty,
    fallback_urls=df_comments["inputUrl"].dropna().unique().tolist(),
)

if governador_selecionado is None:
    st.stop()

# --- APLICAÇÃO DOS FILTROS NO DATAFRAME ---
# inputUrl comparado normalizado (não `==`/`.query` direto) -- reels_clean e
# governor_sentiment vêm do mesmo df_reels bruto sem transformação de URL
# entre os dois, então hoje coincidem byte-a-byte, mas isso não é uma garantia
# formal do pipeline, e já houve um bug real de formatação de URL divergente
# entre tabelas nesta branch (ver governor_engagement vs reels_clean).
universo_ativo = governor_universe_filtrado["inputUrl"].tolist()
df_filtrado_comments = select_governor_rows(df_comments, governador_selecionado, universo_ativo)
df_filtrado_reels = select_governor_rows(df_reels, governador_selecionado, universo_ativo)

# --- PÁGINA PRINCIPAL ---
st.title("📊 Comentários dos Governadores do Brasil")
st.markdown("---")

if df_filtrado_comments.empty:
    st.warning("Nenhum dado encontrado para os filtros selecionados.")
else:
    qtd_reels = int(df_filtrado_comments["id_reel"].nunique())
    qtd_comments = int(df_filtrado_comments["id_comment"].nunique())
    qtd_replies = int(df_filtrado_comments["repliesCount"].sum())
    qtd_likes = int(df_filtrado_comments["likesCount"].sum())

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(label="Qtd de Reels", value=qtd_reels)
    col2.metric(label="Qtd de Comentários", value=qtd_comments)
    col3.metric(label="Total de Replies", value=qtd_replies)
    col4.metric(label="Total de Likes", value=qtd_likes)

    col1, col2 = st.columns(2)
    with col1:
        df_plot = df_filtrado_reels.copy()
        df_plot["shortCode"] = df_plot["shortCode"].astype(str)
        if "Total de Engajamento" not in df_plot.columns:
            df_plot["Total de Engajamento"] = df_plot.get("commentsCount", 0).fillna(
                0
            ) + df_plot.get("likesCount", 0).fillna(0)
        st.plotly_chart(
            plot_top_n_bar(
                df_plot,
                x="Total de Engajamento",
                y="shortCode",
                title="Top 10 Reels por Engajamento",
                top_n=10,
            ),
            width="stretch",
        )

        df_links = (
            df_plot.dropna(subset=["shortCode"])
            .sort_values("Total de Engajamento", ascending=False)
            .head(10)
            .copy()
        )
        df_links["Link"] = "https://www.instagram.com/reel/" + df_links["shortCode"] + "/"
        st.dataframe(
            df_links[["shortCode", "Total de Engajamento", "Link"]],
            column_config={
                "shortCode": "Código do Reel",
                "Link": st.column_config.LinkColumn(
                    "Link", display_text="Abrir no Instagram"
                ),
            },
            hide_index=True,
            width="stretch",
        )

    with col2:
        st.markdown("#### Distribuição de Sentimento")
        if tem_modelagem:
            st.plotly_chart(
                plot_value_counts(
                    df_filtrado_comments,
                    column="sentiment_label",
                    title="Sentimento dos comentários",
                ),
                width="stretch",
            )
        else:
            st.info(
                "Sentimento ainda não gerado para este governador. "
                "Rode `scripts/run_modeling.py` para popular `governor_sentiment`."
            )

    st.markdown("#### Tópicos mais frequentes")
    if tem_modelagem and "Name" in df_filtrado_comments.columns:
        df_topicos = (
            df_filtrado_comments["Name"].value_counts().reset_index(name="count")
        )
        df_topicos.columns = ["Name", "count"]
        st.plotly_chart(
            plot_top_n_bar(
                df_topicos, x="count", y="Name", title="Top tópicos por volume de comentários"
            ),
            width="stretch",
        )
    else:
        st.info(
            "Tópicos ainda não gerados para este governador. "
            "Rode `scripts/run_modeling.py` (e opcionalmente `scripts/refine_topics.py "
            "--run-id <ID>` para refinar os rótulos) para popular `governor_sentiment`."
        )

    st.markdown("#### Clusters dos reels (AutoClusterHPO)")
    if df_clusters.empty:
        st.info(
            "`governor_clusters` ainda não existe. "
            "Rode `scripts/run_modeling.py` para gerá-la."
        )
    else:
        df_reels_com_cluster = df_filtrado_reels.merge(
            df_clusters, left_on="id", right_on="id_reel", how="inner"
        )
        if df_reels_com_cluster.empty:
            st.info("Nenhum reel deste governador tem cluster atribuído.")
        else:
            st.dataframe(
                df_reels_com_cluster.groupby("cluster_label")
                .agg(qtd_reels=("id_reel", "nunique"), algoritmo=("cluster_algo", "first"))
                .reset_index()
            )

    st.markdown("#### Cluster de Perfil por Engajamento (Fase 2)")
    if profile_cluster_directory.empty:
        st.info(
            "`governor_profile_clusters_engagement` ainda não existe. "
            "Rode `scripts/run_profile_clustering_engagement.py` para gerá-la."
        )
    elif governador_selecionado == TODOS_GOVERNADORES:
        st.dataframe(
            governor_universe_filtrado.groupby("cluster_perfil_engajamento")
            .agg(qtd_governadores=("inputUrl", "nunique"))
            .reset_index()
        )
    else:
        linha = governor_universe_filtrado.loc[
            governor_universe_filtrado["inputUrl"] == governador_selecionado
        ]
        cluster_valor = linha["cluster_perfil_engajamento"].iloc[0] if not linha.empty else None
        if cluster_valor is None or pd.isna(cluster_valor):
            st.info("Este governador não tem cluster de perfil atribuído.")
        else:
            st.metric("Cluster de Perfil", int(cluster_valor))

# Para mostrar os dados brutos (opcional)
if st.checkbox("Mostrar dados brutos filtrados"):
    st.subheader("Dados Brutos")
    st.write(df_filtrado_comments)
