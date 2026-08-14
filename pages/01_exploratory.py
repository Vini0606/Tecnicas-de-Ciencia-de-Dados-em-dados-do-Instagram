from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from config import settings
from src.repositories.delta_repository import DeltaRepository
from src.visualization.charts import (
    plot_correlation_heatmap,
    plot_dual_axis,
    plot_top5_bar,
)

st.set_page_config(layout="wide")


@st.cache_data
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    repo = DeltaRepository(gold_dir=settings.GOLD_DIR, silver_dir=settings.SILVER_DIR)
    df_profiles = repo.load_profiles()
    df_comments = repo.load_comments()
    df_reels = repo.load_reels()
    return df_profiles, df_comments, df_reels


df_profiles, df_comments, df_reels = load_data()


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
        plot_top5_bar(
            df_profiles,
            x="FREQUENCIA",
            y="username",
            title="Top 5 — Frequência de postagem",
        ),
        use_container_width=True,
    )
with col_eng:
    st.plotly_chart(
        plot_top5_bar(
            df_profiles,
            x="% ENGAJAMENTO",
            y="username",
            title="Top 5 — % de Engajamento",
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

    # Cria três colunas para organizar os widgets de seleção lado a lado
    col1, col2 = st.columns(2)

    with col1:
        # Widget para selecionar a variável do Eixo X
        x_axis = st.selectbox(
            "Selecione a variável para o Eixo X:",
            options=numeric_cols,
            index=0,  # Define a primeira coluna numérica como padrão
        )

    with col2:
        # Widget para selecionar a variável do Eixo Y
        y_axis = st.selectbox(
            "Selecione a variável para o Eixo Y:",
            options=numeric_cols,
            index=1,  # Define a segunda coluna numérica como padrão
        )

    # Gera o gráfico apenas se as variáveis dos eixos foram selecionadas
    if x_axis and y_axis:
        with st.spinner("Gerando seu gráfico..."):
            # Cria a figura do gráfico de dispersão usando Plotly Express
            fig = px.scatter(
                df_profiles,
                x=x_axis,
                y=y_axis,
                # title=f'Gráfico de Dispersão: {y_axis.capitalize()} vs. {x_axis.capitalize()}',
                # Adiciona mais informações ao passar o mouse sobre os pontos
                hover_data=df_profiles.columns,
                height=1000,  # <--- ADICIONE ESTA LINHA para ajustar a altura
                width=1000,
            )

            # Exibe o gráfico interativo no Streamlit
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Por favor, selecione as variáveis para os eixos X e Y.")
