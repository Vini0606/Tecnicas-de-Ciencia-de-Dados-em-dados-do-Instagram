"""Funil RACE ↔ COBRA (ADR 0020, Frente 2 / issue #94).

Página **presentation-only**: mapeia cada estágio do funil de growth
marketing RACE (Feroz, 2024) a um nível do framework COBRA de engajamento
com marca (Muntinga et al., 2011), lendo as tabelas Gold já produzidas
pelas Fichas 1-8 da ADR 0020 via `DeltaRepository`. Nenhuma métrica de
modelagem é recalculada aqui -- só leitura + agregações triviais de exibição
(soma/contagem/média/groupby), mesma classe de operação já usada em
`02_insights.py` (ex.: "Total de Engajamento" = likes+comentários) e
`03_performance.py` (ex.: `compute_governor_comparison`). Mapeamento fixado
pela ADR:

| Estágio (RACE) | Nível (COBRA) | Métrica |
|---|---|---|
| Reach | — | views/alcance dos reels |
| Act | Consumir | curtidas + distribuição por cluster de conteúdo |
| Convert | Contribuir | comentários + % de sentimento positivo |
| Engage | Criar | volume/engajamento de UGC (posts de terceiros) |

Numeração `05` (não `04`) de propósito -- preserva `01`-`04` intactos, ver
`docs/dashboard/especificacao-reformulacao-growth.md`.
"""

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
    aggregate_ugc_by_governor,
    build_governor_directory,
    enrich_with_governor_metadata,
    render_governor_selector,
    select_governor_rows,
)
from src.dashboard.loaders import (
    load_clusters,
    load_comments,
    load_profiles,
    load_reels,
    load_ugc_mentions,
)

st.set_page_config(
    page_title="Instagram Analytics — Funil",
    page_icon="🧭",
    layout="wide",
)

st.title("🧭 Funil — do Alcance à Criação (RACE ↔ COBRA)")
st.markdown(
    "Cada estágio do funil de growth marketing **RACE** (Feroz, 2024) mapeado a um "
    "nível do framework **COBRA** de engajamento com marca (Muntinga et al., 2011) "
    "-- ADR 0020, Frente 2. Página **presentation-only**: nenhuma métrica é "
    "recalculada aqui, só lida das tabelas Gold já produzidas pelo pipeline."
)
with st.expander("Como ler este funil", expanded=False):
    st.markdown(
        """
| Estágio (RACE) | Nível (COBRA) | Métrica |
|---|---|---|
| **Reach** | — | Views/alcance dos reels |
| **Act** | Consumir | Curtidas + distribuição por cluster de conteúdo |
| **Convert** | Contribuir | Comentários + % de sentimento positivo |
| **Engage** | Criar | Volume/engajamento de UGC (posts de terceiros) |

A linha Engage/Criar depende do piloto do actor de UGC (ADR 0020, Ficha 8 /
issue #93) -- métrica pendente até volume e estabilidade serem confirmados
nos 27 perfis monitorados.
"""
    )
st.markdown("---")

# Seletor global (issue #54 / ADR 0017), mesmo padrão de `03_performance.py`/
# `04_recommendations.py` -- construído sobre `governor_engagement`
# (snapshot mais recente).
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

universo_urls = df_engagement["inputUrl"].dropna().unique().tolist()

# --- Reach ---
st.markdown("## 1. Reach")
st.caption("Nível COBRA: — (fora da tipologia COBRA -- é o topo do funil RACE).")
df_reels = load_reels()
if df_reels.empty or "videoPlayCount" not in df_reels.columns:
    st.info(
        "`reels_clean` ainda não tem `videoPlayCount`. Rode o pipeline de "
        "extração (com reels) primeiro."
    )
else:
    df_reels_selecionado = select_governor_rows(df_reels, governador_selecionado, universo_urls)
    views_total = pd.to_numeric(
        df_reels_selecionado["videoPlayCount"], errors="coerce"
    ).sum()
    st.metric("Views totais (reels)", f"{int(views_total):,}".replace(",", "."))
st.markdown("---")

# --- Act / Consumir ---
st.markdown("## 2. Act")
st.caption("Nível COBRA: Consumir. Métrica: curtidas + distribuição por cluster de conteúdo.")
df_clusters = load_clusters()
if df_reels.empty:
    st.info("`reels_clean` ainda não existe.")
else:
    df_reels_selecionado = select_governor_rows(df_reels, governador_selecionado, universo_urls)
    curtidas_total = pd.to_numeric(
        df_reels_selecionado["likesCount"], errors="coerce"
    ).sum() if "likesCount" in df_reels_selecionado.columns else 0
    st.metric("Curtidas totais (reels)", f"{int(curtidas_total):,}".replace(",", "."))

    if df_clusters.empty:
        st.info(
            "`governor_clusters` ainda não existe. Rode `scripts/run_modeling.py` "
            "para gerá-la."
        )
    else:
        df_reels_cluster = df_reels_selecionado.merge(
            df_clusters, left_on="id", right_on="id_reel", how="inner"
        )
        if df_reels_cluster.empty:
            st.info("Nenhum reel deste governador tem cluster atribuído.")
        else:
            distribuicao = (
                df_reels_cluster.groupby("cluster_label")["id_reel"]
                .nunique()
                .reset_index(name="qtd_reels")
                .sort_values("qtd_reels", ascending=False)
            )
            st.caption(
                "Distribuição bruta por cluster de conteúdo -- a leitura "
                "qualitativa de qual cluster é 'Padrão' (vs. Viral/Longo, "
                "ver seção 'Como isso funciona' da Home) vem do texto do "
                "TCC, não é rotulada automaticamente aqui."
            )
            st.dataframe(distribuicao, hide_index=True, width="stretch")
st.markdown("---")

# --- Convert / Contribuir ---
st.markdown("## 3. Convert")
st.caption("Nível COBRA: Contribuir. Métrica: comentários + % de sentimento positivo.")
df_comments = load_comments()
if df_comments.empty:
    st.info(
        "`governor_sentiment` ainda não tem dados. Rode `scripts/run_modeling.py` "
        "primeiro."
    )
else:
    # `governor_sentiment` acumula 3 fontes desde a Ficha 3 (ADR 0020) --
    # "Convert/Contribuir" é sobre COMENTÁRIO (reação do público), não
    # legenda/transcrição (fala da assessoria); filtra quando a coluna
    # existir, mesmo raciocínio já aplicado por `TopicPriorityScorer`/`NsmScorer`.
    df_comments_only = (
        df_comments[df_comments["fonte"] == "comentario"]
        if "fonte" in df_comments.columns
        else df_comments
    )
    df_comments_selecionado = select_governor_rows(
        df_comments_only, governador_selecionado, universo_urls
    )
    if df_comments_selecionado.empty:
        st.info("Nenhum comentário para este governador ainda.")
    else:
        col_qtd, col_pct = st.columns(2)
        with col_qtd:
            st.metric("Comentários", int(df_comments_selecionado["id_comment"].nunique()))
        with col_pct:
            if "sentiment_label" in df_comments_selecionado.columns:
                pct_positivo = (
                    df_comments_selecionado["sentiment_label"] == "positive"
                ).mean() * 100
                st.metric("% Sentimento Positivo", f"{pct_positivo:.1f}%")
            else:
                st.metric("% Sentimento Positivo", "—")
st.markdown("---")

# --- Engage / Criar ---
st.markdown("## 4. Engage")
st.caption(
    "Nível COBRA: Criar. Métrica: volume/engajamento de UGC (posts de "
    "terceiros marcando/mencionando o perfil) -- ADR 0020, Ficha 8."
)
df_ugc = load_ugc_mentions()
if df_ugc.empty:
    st.info(
        "`governor_ugc_mentions` ainda não existe -- piloto do actor de UGC "
        "pendente (ADR 0020, Ficha 8 / issue #93). A métrica de Engage/Criar "
        "fica pendente até o piloto confirmar volume/estabilidade nos 27 "
        "perfis monitorados."
    )
else:
    # `aggregate_ugc_by_governor` é a "view" pura já documentada em
    # `GovernorUGCAggregator` (reaproveitada aqui via `src.dashboard.filters`,
    # não recalculada): a agregação (contagem/média/% orgânico) já é código
    # de produção testado em `tests/test_ugc_mentions_aggregator.py`, esta
    # página só a exibe.
    agregado_ugc = aggregate_ugc_by_governor(df_ugc)
    if governador_selecionado == TODOS_GOVERNADORES:
        st.dataframe(agregado_ugc, hide_index=True, width="stretch")
    else:
        linha_engagement = select_governor_rows(
            df_engagement, governador_selecionado, universo_urls
        )
        username_selecionado = (
            linha_engagement["username"].iloc[0] if not linha_engagement.empty else None
        )
        linha_ugc = agregado_ugc[agregado_ugc["governor_username"] == username_selecionado]
        if linha_ugc.empty:
            st.info("Nenhuma menção de UGC encontrada para este governador ainda.")
        else:
            linha_ugc = linha_ugc.iloc[0]
            col_count, col_avg, col_pct = st.columns(3)
            col_count.metric("Posts de UGC orgânicos", int(linha_ugc["count_organic"]))
            col_avg.metric(
                "Engajamento médio (orgânico)", f"{linha_ugc['avg_engagement_organic']:.1f}"
            )
            col_pct.metric("% Orgânico", f"{linha_ugc['pct_organic'] * 100:.0f}%")
