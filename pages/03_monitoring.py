from __future__ import annotations

import os
import sys

import streamlit as st

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from config import settings
from src.dashboard.filters import (
    TODOS_GOVERNADORES,
    build_governor_directory,
    enrich_with_governor_metadata,
    render_governor_selector,
    select_governor_rows,
)
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

# Seletor global (issue #54 / ADR 0017): mesmo widget/`session_state`
# compartilhado com `02_modeling.py` -- selecionar um governador em qualquer
# página persiste ao navegar para esta. Precisa ficar FORA do
# `st.fragment` abaixo -- o Streamlit não permite um widget de `st.sidebar`
# criado de dentro de um fragment escrever num container fora dele
# (`StreamlitFragmentWidgetsNotAllowedOutsideError`). `df_history` é
# recarregado de novo dentro do fragment (cache-hit via `st.cache_data`,
# barato) para que o corpo dos gráficos continue re-checando frescor a cada
# tick, independente deste carregamento aqui só para montar o universo do
# seletor.
df_history_para_seletor = load_engagement_history()
if df_history_para_seletor.empty:
    governador_selecionado = TODOS_GOVERNADORES
else:
    governor_universe = df_history_para_seletor[["inputUrl"]].dropna().drop_duplicates()
    governor_universe_enriched = enrich_with_governor_metadata(governor_universe)
    governador_selecionado = render_governor_selector(
        governor_universe_enriched,
        directory_exists=not build_governor_directory().empty,
        fallback_urls=df_history_para_seletor["inputUrl"].dropna().unique().tolist(),
    )
    if governador_selecionado is None:
        governador_selecionado = TODOS_GOVERNADORES


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

    universo_urls = df_history["inputUrl"].dropna().unique().tolist()
    df_filtrado = select_governor_rows(df_history, governador_selecionado, universo_urls)

    if df_filtrado.empty:
        st.warning("Nenhum dado para o governador selecionado.")
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
