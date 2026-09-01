from __future__ import annotations

import os
import sys

import streamlit as st

ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.dashboard.loaders import load_comments, load_profiles, load_reels

st.set_page_config(
    page_title="Instagram Analytics — Governadores",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Instagram Analytics — Governadores do Brasil")
st.markdown(
    "Acompanhe engajamento, sentimento e tópicos discutidos nos perfis de Instagram dos "
    "**27 governadores do Brasil** — uma visão consolidada pra quem acompanha comunicação "
    "e métricas de redes sociais no setor público."
)

df_profiles = load_profiles()
df_reels = load_reels()
df_comments = load_comments()

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Governadores", len(df_profiles) if not df_profiles.empty else "—")
with col2:
    st.metric("Reels analisados", len(df_reels) if not df_reels.empty else "—")
with col3:
    st.metric("Comentários analisados", len(df_comments) if not df_comments.empty else "—")
with col4:
    if not df_comments.empty and "sentiment_label" in df_comments.columns:
        pct_positivo = (df_comments["sentiment_label"] == "positive").mean() * 100
        st.metric("% Sentimento Positivo", f"{pct_positivo:.1f}%")
    else:
        st.metric("% Sentimento Positivo", "—")

st.markdown("---")

st.markdown("### Navegue pelas análises")
nav1, nav2, nav3 = st.columns(3)
with nav1:
    st.page_link(
        "pages/01_exploratory.py",
        label="Exploratório — perfis, engajamento e correlações",
        icon="📊",
    )
with nav2:
    st.page_link(
        "pages/02_modeling.py",
        label="Modelagem — sentimento, tópicos e clusters",
        icon="📈",
    )
with nav3:
    st.page_link(
        "pages/03_monitoring.py",
        label="Monitoramento — tendência de engajamento ao longo do tempo",
        icon="📡",
    )

st.markdown("---")

st.markdown(
    "Por trás dos números: um pipeline de NLP combina PCA, clusterização, "
    "análise de sentimento e modelagem de tópicos (BERTopic) para chegar "
    "nessas métricas."
)
with st.expander("Como isso funciona", expanded=False):
    st.markdown(
        """
O pipeline aplica quatro técnicas em sequência, cada uma alimentando a seguinte:

1. **PCA** reduz as métricas de engajamento e duração dos reels a dois componentes.
2. **`AutoClusterHPO`** (peça original do trabalho) testa KMeans, DBSCAN e
   Agglomerative Clustering automaticamente, escolhendo o melhor via um score
   CVI combinado (Silhouette + Calinski-Harabasz + Davies-Bouldin).
3. **Análise de sentimento** classifica os comentários em positivo, neutro ou
   negativo (`cardiffnlp/twitter-xlm-roberta-base-sentiment`).
4. **BERTopic** extrai os temas discutidos nos comentários.

O achado central, em uma frase: **o conteúdo padrão é aprovado, o viral é
debatido, e o longo é ignorado** — uma leitura que nenhuma das três técnicas
produz isoladamente. A metodologia completa e os resultados detalhados estão
no `README.md` do repositório (TCC de Ciência de Dados e Inteligência
Artificial, IESB).
"""
    )
