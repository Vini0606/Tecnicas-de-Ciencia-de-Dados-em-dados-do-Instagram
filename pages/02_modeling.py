from __future__ import annotations

import os
import sys

import streamlit as st

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from config import settings
from src.repositories.delta_repository import DeltaRepository
from src.visualization.charts import plot_top_n_bar

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Instagram Analytics — Modelagem",
    page_icon="📈",
    layout="wide",
)


@st.cache_data
def load_data():
    repo = DeltaRepository(settings.GOLD_DIR, settings.SILVER_DIR)
    return repo.load_comments(), repo.load_reels()


df_comments, df_reels = load_data()

# --- BARRA LATERAL (SIDEBAR) PARA FILTROS ---
st.sidebar.header("Filtros do Dashboard")

governador_selecionado = st.sidebar.selectbox(
    "Selecione o Governador:",
    options=df_comments["inputUrl"].dropna().unique(),
)

# --- APLICAÇÃO DOS FILTROS NO DATAFRAME ---
df_filtrado_comments = df_comments.query("inputUrl == @governador_selecionado")

df_filtrado_reels = df_reels.query("inputUrl == @governador_selecionado")

# --- PÁGINA PRINCIPAL ---
st.title("📊 Comentários dos Governadores do Brasil")
st.markdown("---")

if df_filtrado_comments.empty:
    st.warning("Nenhum dado encontrado para os filtros selecionados.")
else:
    qtd_reels = int(df_filtrado_comments["id_reel"].nunique())
    qtd_comments = int(df_filtrado_comments["id_comment"].nunique())
    qtd_replies = int(df_filtrado_comments["repliesCount"].sum())
    qtd_likes = (
        int(df_filtrado_comments["likesCount_comment"].sum())
        if "likesCount_comment" in df_filtrado_comments.columns
        else int(df_filtrado_comments["likesCount"].sum())
    )

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

    with col2:
        st.markdown("#### Resumo do Tópico")
        if not df_filtrado_comments.empty:
            name_col = (
                "ownerFullName"
                if "ownerFullName" in df_filtrado_comments.columns
                else "owner.username"
                if "owner.username" in df_filtrado_comments.columns
                else None
            )
            if name_col:
                st.write(df_filtrado_comments[name_col].iloc[0])

        cols = [
            col
            for col in [
                "timestamp_comment",
                "owner.username",
                "text",
                "repliesCount",
                "likesCount_comment",
            ]
            if col in df_filtrado_comments.columns
        ]
        if cols:
            st.dataframe(df_filtrado_comments[cols])
        else:
            st.info("Não há colunas adicionais disponíveis para exibição.")

# Para mostrar os dados brutos (opcional)
if st.checkbox("Mostrar dados brutos filtrados"):
    st.subheader("Dados Brutos")
    st.write(df_filtrado_comments)
