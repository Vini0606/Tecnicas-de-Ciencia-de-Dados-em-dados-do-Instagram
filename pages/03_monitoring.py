from __future__ import annotations

import os
import sys

import streamlit as st

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from config import settings
from src.dashboard.loaders import load_engagement_history
from src.visualization.charts import plot_engagement_trend

st.set_page_config(
    page_title="Instagram Analytics — Monitoramento",
    page_icon="📡",
    layout="wide",
)

st.title("📡 Monitoramento — Governadores do Brasil")
st.markdown(
    "Tendência de engajamento a partir de `governor_engagement_history` "
    "(uma linha por governador a cada execução do pipeline). Esta seção "
    f"recarrega sozinha a cada {settings.DASHBOARD_REFRESH_SECONDS}s, sem "
    "precisar reiniciar o app — ver ADR 0016."
)
st.markdown("---")


@st.fragment(run_every=f"{settings.DASHBOARD_REFRESH_SECONDS}s")
def render_monitoring() -> None:
    df_history = load_engagement_history()

    if df_history.empty:
        st.info(
            "`governor_engagement_history` ainda não tem dados. Rode o pipeline "
            "(`uv run python pipeline.py`) para começar a acumular histórico."
        )
        return

    ultima_execucao = df_history.loc[df_history["_generated_at"].idxmax()]
    st.caption(
        f"Última atualização: {ultima_execucao['_generated_at']} "
        f"(run_id: `{ultima_execucao['_run_id']}`)"
    )

    governadores_disponiveis = sorted(df_history["username"].dropna().unique())
    governadores_selecionados = st.multiselect(
        "Governadores",
        options=governadores_disponiveis,
        default=governadores_disponiveis,
    )
    df_filtrado = df_history[df_history["username"].isin(governadores_selecionados)]

    if df_filtrado.empty:
        st.warning("Nenhum governador selecionado.")
        return

    st.plotly_chart(
        plot_engagement_trend(
            df_filtrado,
            y_col="TOTAL ENGAJAMENTO",
            title="Tendência de Engajamento Total",
        ),
        width="stretch",
    )
    st.plotly_chart(
        plot_engagement_trend(
            df_filtrado,
            y_col="% ENGAJAMENTO",
            title="Tendência de % de Engajamento",
        ),
        width="stretch",
    )


render_monitoring()
