from __future__ import annotations

import os
import sys

import streamlit as st

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from config import settings
from src.dashboard.comparisons import compute_governor_comparison
from src.dashboard.filters import (
    TODOS_GOVERNADORES,
    build_governor_directory,
    build_governor_label_map,
    enrich_with_governor_metadata,
    render_governor_selector,
    select_governor_rows,
)
from src.dashboard.loaders import load_engagement_history, load_profiles
from src.visualization.charts import (
    plot_engagement_group_summary_trend,
    plot_engagement_trend_with_group_context,
)

st.set_page_config(
    page_title="Instagram Analytics — Performance",
    page_icon="🎯",
    layout="wide",
)

st.title("🎯 Performance — Governadores do Brasil")
st.markdown(
    "Como o governador selecionado está indo em relação aos seus pares, mais a "
    "tendência de engajamento ao longo do tempo. Esta seção recarrega sozinha a "
    f"cada {settings.DASHBOARD_REFRESH_SECONDS}s, sem precisar reiniciar o app — "
    "ver ADR 0016."
)
st.markdown("---")

HISTORICO_VAZIO_MSG = (
    "`governor_engagement_history` ainda não tem dados. Rode o pipeline "
    "(`uv run python pipeline.py`) para começar a acumular histórico."
)

# Métricas brutas de governor_engagement usadas na comparação (issue #59) --
# todas as colunas numéricas não-identificadoras do schema, decisão do
# usuário de não curar um subconjunto. Direção do ranking é uniforme (maior
# = melhor/rank 1) para todas -- RECENCIA já vem invertida
# (1/(dias_desde_ultimo+1)) do EngagementAggregator.
METRICAS_COMPARACAO = [
    "followersCount",
    "followsCount",
    "postsCount",
    "TOTAL ENGAJAMENTO",
    "% ENGAJAMENTO",
    "RECENCIA",
    "FREQUENCIA",
    "commentsSum",
    "likesSum",
    "count",
]

# Seletor global (issue #54 / ADR 0017): mesmo widget/`session_state`
# compartilhado com `02_insights.py` -- selecionar um governador em qualquer
# página persiste ao navegar para esta. Construído sobre `governor_engagement`
# (snapshot mais recente, sempre existe se o pipeline já rodou uma vez),não
# sobre o histórico -- não depende de haver mais de uma execução acumulada
# pra montar o universo de opções.
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
# Contrato de render_governor_selector (ver docstring): None = "pare a
# página", mesmo tratamento de 02_insights.py.
if governador_selecionado is None:
    st.stop()

# Nome de exibição do governador selecionado (issue #68), rótulo da linha em
# destaque no gráfico de tendência -- mesmo helper de resolução de nome
# usado por `render_governor_selector`, não uma segunda implementação.
nome_governador_selecionado = build_governor_label_map(governor_universe_enriched).get(
    governador_selecionado, governador_selecionado
)

if governador_selecionado != TODOS_GOVERNADORES:
    st.markdown("### Como você está indo vs. seus pares")
    df_comparacao = compute_governor_comparison(
        df_engagement, governador_selecionado, METRICAS_COMPARACAO
    )
    if df_comparacao.empty:
        st.info("Sem dado suficiente para comparar este governador com os demais ainda.")
    else:
        # Grade de 5 colunas por linha -- calculado a partir do tamanho real
        # de df_comparacao (não hardcoded em 2 linhas de 5), para não
        # silenciosamente cortar métricas se METRICAS_COMPARACAO crescer.
        METRICAS_POR_LINHA = 5
        linhas_de_metricas = [
            df_comparacao.iloc[i : i + METRICAS_POR_LINHA]
            for i in range(0, len(df_comparacao), METRICAS_POR_LINHA)
        ]
        for linha_de_metricas in linhas_de_metricas:
            cols = st.columns(len(linha_de_metricas))
            for col, (_, metrica) in zip(cols, linha_de_metricas.iterrows()):
                with col:
                    # Métricas de contagem (seguidores, posts etc.) são
                    # inteiras -- "1.000" lê melhor que "1000.00".
                    is_inteira = float(metrica["value"]).is_integer()
                    valor_fmt = (
                        f"{metrica['value']:,.0f}" if is_inteira else f"{metrica['value']:.2f}"
                    )
                    delta_fmt = (
                        f"{metrica['delta']:+,.0f}" if is_inteira else f"{metrica['delta']:+.2f}"
                    )
                    st.metric(
                        metrica["metric"],
                        value=valor_fmt,
                        delta=f"{delta_fmt} vs. média (#{metrica['rank']} de {metrica['total']})",
                    )
    st.markdown("---")


@st.fragment(run_every=f"{settings.DASHBOARD_REFRESH_SECONDS}s")
def render_performance_trend() -> None:
    df_history = load_engagement_history()

    if df_history.empty:
        st.info(HISTORICO_VAZIO_MSG)
        return

    ultima_execucao = df_history.loc[df_history["_generated_at"].idxmax()]
    st.caption(
        f"Última atualização: {ultima_execucao['_generated_at']} "
        f"(run_id: `{ultima_execucao['_run_id']}`)"
    )

    if governador_selecionado == TODOS_GOVERNADORES:
        # Issue #68: uma linha por governador (até 27 séries/cores no mesmo
        # gráfico) estoura o teto categórico da paleta e fica ilegível --
        # agrega em Média/Mediana do grupo em vez de plotar todo mundo.
        st.plotly_chart(
            plot_engagement_group_summary_trend(
                df_history,
                y_col="TOTAL ENGAJAMENTO",
                title="Tendência de Engajamento Total — Média/Mediana do grupo",
            ),
            width="stretch",
        )
        st.plotly_chart(
            plot_engagement_group_summary_trend(
                df_history,
                y_col="% ENGAJAMENTO",
                title="Tendência de % de Engajamento — Média/Mediana do grupo",
            ),
            width="stretch",
        )
        return

    universo_urls = df_history["inputUrl"].dropna().unique().tolist()
    df_filtrado = select_governor_rows(df_history, governador_selecionado, universo_urls)

    if df_filtrado.empty:
        st.warning("Nenhum dado para o governador selecionado.")
        return

    st.plotly_chart(
        plot_engagement_trend_with_group_context(
            df_filtrado,
            df_history,
            y_col="TOTAL ENGAJAMENTO",
            governor_label=nome_governador_selecionado,
            title="Tendência de Engajamento Total",
        ),
        width="stretch",
    )
    st.plotly_chart(
        plot_engagement_trend_with_group_context(
            df_filtrado,
            df_history,
            y_col="% ENGAJAMENTO",
            governor_label=nome_governador_selecionado,
            title="Tendência de % de Engajamento",
        ),
        width="stretch",
    )


render_performance_trend()
