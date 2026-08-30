from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import streamlit as st

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.dashboard.filters import (
    apply_group_filters,
    build_cluster_membership,
    build_governor_directory,
    build_profile_cluster_directory,
    enrich_with_governor_metadata,
    enrich_with_profile_cluster,
    render_group_filters,
    render_unmatched_warning,
)
from src.dashboard.loaders import load_profiles
from src.visualization.charts import (
    plot_correlation_heatmap,
    plot_dual_axis,
    plot_scatter,
    plot_top_n_bar,
)

st.set_page_config(
    page_title="Instagram Analytics — Exploratório",
    page_icon="📊",
    layout="wide",
)


governor_directory = build_governor_directory()
cluster_membership = build_cluster_membership()
profile_cluster_directory = build_profile_cluster_directory()
filters = render_group_filters(governor_directory, cluster_membership, profile_cluster_directory)

df_profiles_enriched = enrich_with_governor_metadata(load_profiles())
df_profiles_enriched = enrich_with_profile_cluster(df_profiles_enriched)
render_unmatched_warning(df_profiles_enriched)
df_profiles = apply_group_filters(df_profiles_enriched, filters, cluster_membership)

if df_profiles.empty:
    st.warning("Nenhum governador corresponde aos filtros de grupo selecionados.")
    st.stop()


def media(df: pd.DataFrame, coluna: str) -> float:
    """Média de uma coluna, ou NaN quando ela não existe no DataFrame."""
    if coluna not in df.columns:
        return float("nan")
    return pd.to_numeric(df[coluna], errors="coerce").mean()


def media_por_publicacao(df: pd.DataFrame, total: str) -> float:
    """Média por publicação, protegida contra colunas ausentes e divisão por zero."""
    if total not in df.columns or "count" not in df.columns:
        return float("nan")
    numerador = pd.to_numeric(df[total], errors="coerce")
    denominador = pd.to_numeric(df["count"], errors="coerce")
    return numerador.div(denominador.where(denominador > 0)).mean()


# --- MÉTRICAS ---
col1, col2, col3, col4, col5, col6 = st.columns(6)
with col1:
    st.metric(label="Média de Seguidores", value=round(media(df_profiles, "followersCount"), 2))
with col2:
    st.metric(label="Média de Seguidos", value=round(media(df_profiles, "followsCount"), 2))
with col3:
    st.metric(label="Média de Publicações", value=round(media(df_profiles, "postsCount"), 2))
with col4:
    st.metric(
        label="Média de Comentários p/ Publicação",
        value=round(media_por_publicacao(df_profiles, "commentsSum"), 2),
    )
with col5:
    st.metric(
        label="Média de Likes p/ Publicação",
        value=round(media_por_publicacao(df_profiles, "likesSum"), 2),
    )
with col6:
    st.metric(
        label="Média de % de Engajamento",
        value=round(media(df_profiles, "% ENGAJAMENTO"), 2),
    )


# --- GRÁFICOS ---
col_freq, col_eng = st.columns(2)
with col_freq:
    st.plotly_chart(
        plot_top_n_bar(
            df_profiles,
            x="FREQUENCIA",
            y="username",
            title="Top 5 — Frequência de postagem",
            top_n=5,
        ),
        use_container_width=True,
    )
with col_eng:
    st.plotly_chart(
        plot_top_n_bar(
            df_profiles,
            x="% ENGAJAMENTO",
            y="username",
            title="Top 5 — % de Engajamento",
            top_n=5,
        ),
        use_container_width=True,
    )


st.plotly_chart(
    plot_dual_axis(
        df_profiles,
        bar_col="followersCount",
        line_col="% ENGAJAMENTO",
        label_col="username",
        bar_name="Nº de Seguidores",
        line_name="% de Engajamento",
        title="Seguidores vs. Engajamento por Perfil",
    ),
    use_container_width=True,
)

st.plotly_chart(
    plot_dual_axis(
        df_profiles,
        bar_col="followsCount",
        line_col="% ENGAJAMENTO",
        label_col="username",
        bar_name="Nº de Seguidos",
        line_name="% de Engajamento",
        title="Seguidos vs. Engajamento por Perfil",
    ),
    use_container_width=True,
)

st.plotly_chart(
    plot_dual_axis(
        df_profiles,
        bar_col="postsCount",
        line_col="% ENGAJAMENTO",
        label_col="username",
        bar_name="Nº de Posts",
        line_name="% de Engajamento",
        title="Posts vs. Engajamento por Perfil",
    ),
    use_container_width=True,
)


numeric_cols = df_profiles.select_dtypes(include=np.number).columns.tolist()

corr_method = st.selectbox(
    "Escolha o método de correlação:", ("pearson", "kendall", "spearman")
)

if not numeric_cols:
    st.warning("Nenhuma coluna numérica foi encontrada nos dados para gerar a matriz.")
else:
    corr_matrix = df_profiles[numeric_cols].corr(method=corr_method)
    with st.spinner("Gerando o heatmap..."):
        st.plotly_chart(
            plot_correlation_heatmap(df_profiles, method=corr_method),
            use_container_width=True,
        )
        if st.checkbox("Mostrar tabela da matriz de correlação"):
            st.dataframe(corr_matrix)

    # Verifica se há colunas numéricas suficientes
    if len(numeric_cols) < 2:
        st.error(
            "Erro: Seus dados precisam ter pelo menos duas colunas numéricas para criar um gráfico de dispersão."
        )
        st.stop()  # Interrompe a execução do script se não houver colunas suficientes

    # Gráfico à esquerda (75%), seletores de eixo à direita (25%)
    col_scatter, col_selectors = st.columns([3, 1])

    with col_selectors:
        # Widget para selecionar a variável do Eixo X
        x_axis = st.selectbox(
            "Eixo X:",
            options=numeric_cols,
            index=0,  # Define a primeira coluna numérica como padrão
        )

        # Widget para selecionar a variável do Eixo Y
        y_axis = st.selectbox(
            "Eixo Y:",
            options=numeric_cols,
            index=1,  # Define a segunda coluna numérica como padrão
        )

    with col_scatter:
        # Gera o gráfico apenas se as variáveis dos eixos foram selecionadas
        if x_axis and y_axis:
            with st.spinner("Gerando seu gráfico..."):
                fig = plot_scatter(df_profiles, x=x_axis, y=y_axis, height=500)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Por favor, selecione as variáveis para os eixos X e Y.")
