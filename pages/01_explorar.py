from __future__ import annotations

import os
import sys

import numpy as np
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
from src.visualization.charts import plot_correlation_heatmap, plot_scatter

st.set_page_config(
    page_title="Instagram Analytics — Explorar",
    page_icon="🔍",
    layout="wide",
)

st.title("🔍 Explorar — Governadores do Brasil")
st.markdown(
    "Correlações livres entre métricas do grupo filtrado — escolha o método de "
    "correlação e os eixos do gráfico de dispersão para investigar relações que "
    "as outras páginas não cobrem diretamente."
)
st.markdown("---")

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
