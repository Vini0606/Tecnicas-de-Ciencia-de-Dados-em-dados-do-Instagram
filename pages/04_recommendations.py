from __future__ import annotations

import os
import sys

import streamlit as st

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.dashboard.filters import (
    TODOS_GOVERNADORES,
    build_governor_directory,
    build_profile_cluster_directory,
    enrich_with_governor_metadata,
    render_governor_selector,
)
from src.dashboard.loaders import (
    load_comments,
    load_engagement_history,
    load_profiles,
    load_reels,
    load_sentiment_history,
)
from src.dashboard.recommendations import compute_recommendations

st.set_page_config(
    page_title="Instagram Analytics — Recommendations",
    page_icon="✅",
    layout="wide",
)

st.title("✅ Recommendations — Governadores do Brasil")
st.markdown(
    "Alertas gerados por regras determinísticas sobre os seus próprios dados — "
    "sem redação por IA, só fatos calculados a partir do que já existe no "
    "dashboard (tendência de engajamento, sentimento, tópicos e comparação "
    "com pares de cluster)."
)
st.markdown("---")

# Seletor global (issue #54 / ADR 0017), mesmo padrão de 02_insights.py/
# 03_performance.py -- universo a partir de governor_engagement.
df_engagement = load_profiles()
if df_engagement.empty:
    st.info(
        "`governor_engagement` ainda não tem dados. Rode o pipeline "
        "(`uv run python pipeline.py`) primeiro."
    )
    st.stop()

governor_universe = df_engagement[["inputUrl"]].dropna().drop_duplicates()
governor_universe_enriched = enrich_with_governor_metadata(governor_universe)
governador_selecionado = render_governor_selector(
    governor_universe_enriched,
    directory_exists=not build_governor_directory().empty,
    fallback_urls=df_engagement["inputUrl"].dropna().unique().tolist(),
)
if governador_selecionado is None:
    st.stop()

# Recomendações são por definição individuais -- não fazem sentido agregadas
# pra "Todos os Governadores" (issue #65, user story 8).
if governador_selecionado == TODOS_GOVERNADORES:
    st.info("Selecione um governador específico na barra lateral para ver as recomendações dele.")
    st.stop()

df_engagement_history = load_engagement_history()
df_sentiment = load_comments()
df_sentiment_history = load_sentiment_history()
df_reels = load_reels()
df_profile_clusters = build_profile_cluster_directory()

achados = compute_recommendations(
    governador_selecionado,
    df_engagement,
    df_engagement_history,
    df_sentiment,
    df_sentiment_history,
    df_reels,
    df_profile_clusters,
)

if not achados:
    st.success("Nenhum alerta identificado para este governador no momento.")
else:
    for mensagem in achados:
        st.warning(mensagem)
