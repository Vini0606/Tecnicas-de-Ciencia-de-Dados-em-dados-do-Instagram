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
    apply_group_filters,
    build_cluster_membership,
    build_governor_directory,
    build_profile_cluster_directory,
    enrich_with_governor_metadata,
    enrich_with_profile_cluster,
    render_governor_selector,
    render_group_filters,
    render_unmatched_warning,
    select_governor_rows,
)
from src.dashboard.loaders import (
    load_clusters,
    load_comments,
    load_discourse_topics,
    load_posts,
    load_reels,
    load_sentiment_history,
    load_topic_priority_score,
)
from src.visualization.charts import (
    plot_sentiment_diverging_bar,
    plot_sentiment_trend,
    plot_top_n_bar,
)

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Instagram Analytics — Insights",
    page_icon="💡",
    layout="wide",
)


df_comments, df_reels, df_clusters = load_comments(), load_reels(), load_clusters()
tem_modelagem = "sentiment_label" in df_comments.columns

# --- BARRA LATERAL (SIDEBAR) PARA FILTROS ---
st.sidebar.header("Filtros do Dashboard")

governor_directory = build_governor_directory()
cluster_membership = build_cluster_membership()
profile_cluster_directory = build_profile_cluster_directory()
filters = render_group_filters(governor_directory, cluster_membership, profile_cluster_directory)

# O universo de opções do seletor vem do próprio inputUrl de df_comments (não
# do xlsx) -- governor_sentiment/reels_clean gravam a URL sem barra final,
# governors_metadata (xlsx) grava com barra final; usar o valor do xlsx aqui
# faria `select_governor_rows` abaixo nunca encontrar nada. nome/uf/regiao/
# partido/cluster_perfil_engajamento continuam vindo do xlsx/Gold, só que via
# join normalizado.
governor_universe = df_comments[["inputUrl"]].dropna().drop_duplicates()
governor_universe_enriched = enrich_with_governor_metadata(governor_universe)
governor_universe_enriched = enrich_with_profile_cluster(governor_universe_enriched)
render_unmatched_warning(governor_universe_enriched)
governor_universe_filtrado = apply_group_filters(
    governor_universe_enriched, filters, cluster_membership
)

st.sidebar.markdown("---")
governador_selecionado = render_governor_selector(
    governor_universe_filtrado,
    directory_exists=not governor_directory.empty,
    fallback_urls=df_comments["inputUrl"].dropna().unique().tolist(),
)

if governador_selecionado is None:
    st.stop()

# --- APLICAÇÃO DOS FILTROS NO DATAFRAME ---
# inputUrl comparado normalizado (não `==`/`.query` direto) -- reels_clean e
# governor_sentiment vêm do mesmo df_reels bruto sem transformação de URL
# entre os dois, então hoje coincidem byte-a-byte, mas isso não é uma garantia
# formal do pipeline, e já houve um bug real de formatação de URL divergente
# entre tabelas nesta branch (ver governor_engagement vs reels_clean).
universo_ativo = governor_universe_filtrado["inputUrl"].tolist()
df_filtrado_comments = select_governor_rows(df_comments, governador_selecionado, universo_ativo)
df_filtrado_reels = select_governor_rows(df_reels, governador_selecionado, universo_ativo)

# ADR 0020 (Ficha 2) / issue #94: posts do Feed, para "Padrões de conteúdo
# (Reels e Feed)" abaixo -- `load_posts()` degrada para DataFrame vazio se
# `posts_clean` ainda não existir, então este filtro nunca quebra a página.
df_posts = load_posts()
df_filtrado_posts = (
    select_governor_rows(df_posts, governador_selecionado, universo_ativo)
    if not df_posts.empty
    else pd.DataFrame()
)

# --- PÁGINA PRINCIPAL ---
st.title("💡 Insights — Governadores do Brasil")
st.markdown("---")

# ADR 0020 (Ficha 6) / issue #91, seção adicionada pela issue #94: Score ICE
# de priorização de tópicos -- ranking GLOBAL de tópicos de COMENTÁRIO (não
# por governador selecionado), por isso fica FORA do bloco condicionado a
# `df_filtrado_comments` abaixo (mesma decisão da especificação de
# dashboard: "tabela top temas a produzir" vale para a base toda, não muda
# com o seletor individual de governador).
st.markdown(
    "#### Prioridade de Temas (o que produzir a seguir)",
    help=(
        "Score ICE = Impacto × Confiança × Facilidade, 100% automatizado -- "
        "ADR 0020, Ficha 6. Ranking global de tópicos de comentário, não "
        "filtrado pelo governador selecionado na barra lateral."
    ),
)
df_topic_priority = load_topic_priority_score()
if df_topic_priority.empty:
    st.info(
        "`topic_priority_score` ainda não existe. Rode `scripts/run_modeling.py` "
        "para gerá-la."
    )
else:
    colunas_score = [
        c
        for c in ["Name", "impacto", "confianca", "facilidade", "score"]
        if c in df_topic_priority.columns
    ]
    st.dataframe(
        df_topic_priority.sort_values("score", ascending=False)[colunas_score],
        hide_index=True,
        width="stretch",
    )
st.markdown("---")

if df_filtrado_comments.empty:
    st.warning("Nenhum dado encontrado para os filtros selecionados.")
else:
    qtd_reels = int(df_filtrado_comments["id_reel"].nunique())
    qtd_comments = int(df_filtrado_comments["id_comment"].nunique())
    qtd_replies = int(df_filtrado_comments["repliesCount"].sum())
    qtd_likes = int(df_filtrado_comments["likesCount"].sum())

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

        df_links = (
            df_plot.dropna(subset=["shortCode"])
            .sort_values("Total de Engajamento", ascending=False)
            .head(10)
            .copy()
        )
        df_links["Link"] = "https://www.instagram.com/reel/" + df_links["shortCode"] + "/"
        st.dataframe(
            df_links[["shortCode", "Total de Engajamento", "Link"]],
            column_config={
                "shortCode": "Código do Reel",
                "Link": st.column_config.LinkColumn(
                    "Link", display_text="Abrir no Instagram"
                ),
            },
            hide_index=True,
            width="stretch",
        )

    with col2:
        st.markdown("#### Distribuição de Sentimento")
        if tem_modelagem:
            st.plotly_chart(
                plot_sentiment_diverging_bar(
                    df_filtrado_comments,
                    column="sentiment_label",
                    title="Sentimento dos comentários",
                ),
                width="stretch",
            )
        else:
            st.info(
                "Sentimento ainda não gerado para este governador. "
                "Rode `scripts/run_modeling.py` para popular `governor_sentiment`."
            )

    # Tendência de sentimento (issue #61 / issue #52): narrativa por
    # governador ("o sentimento sobre você está melhorando"), não comparação
    # entre pares -- por isso só aparece com um governador específico
    # selecionado, mesmo raciocínio já usado nos cards da Performance.
    if governador_selecionado != TODOS_GOVERNADORES:
        st.markdown("#### Tendência de sentimento")
        df_sentiment_history = load_sentiment_history()
        df_sentiment_history_filtrado = select_governor_rows(
            df_sentiment_history, governador_selecionado, universo_ativo
        )
        if df_sentiment_history_filtrado.empty:
            st.info(
                "Ainda não há histórico de sentimento suficiente para este "
                "governador. Cada execução de `scripts/run_modeling.py` "
                "acrescenta um ponto novo."
            )
        else:
            st.plotly_chart(
                plot_sentiment_trend(
                    df_sentiment_history_filtrado,
                    title="% de comentários positivos ao longo do tempo",
                ),
                width="stretch",
            )

    st.markdown("#### Tópicos mais frequentes")
    df_topicos = None
    if tem_modelagem and "Name" in df_filtrado_comments.columns:
        df_topicos = (
            df_filtrado_comments["Name"].value_counts().reset_index(name="count")
        )
        df_topicos.columns = ["Name", "count"]
        st.plotly_chart(
            plot_top_n_bar(
                df_topicos, x="count", y="Name", title="Top tópicos por volume de comentários"
            ),
            width="stretch",
        )
    else:
        st.info(
            "Tópicos ainda não gerados para este governador. "
            "Rode `scripts/run_modeling.py` (e opcionalmente `scripts/refine_topics.py "
            "--run-id <ID>` para refinar os rótulos) para popular `governor_sentiment`."
        )

    # ADR 0020 (Ficha 4) / issue #89, seção adicionada pela issue #94:
    # "Discurso vs. Reação" -- do que a assessoria FALA (governor_discourse_topics,
    # BERTopic sobre legenda+transcrição) lado a lado com do que o PÚBLICO fala
    # (df_topicos, já calculado acima a partir dos comentários deste governador).
    st.markdown(
        "#### Discurso vs. Reação",
        help=(
            "Contraste entre o que a assessoria produz (legendas/"
            "transcrições) e o que o público comenta -- ADR 0020, Ficha 4."
        ),
    )
    df_discourse_topics = load_discourse_topics()
    col_discurso, col_reacao = st.columns(2)
    with col_discurso:
        st.markdown("##### Do que a assessoria fala")
        if df_discourse_topics.empty:
            st.info(
                "`governor_discourse_topics` ainda não existe. Rode "
                "`scripts/run_modeling.py` (estágio de discurso) para gerá-la."
            )
        else:
            df_discurso_filtrado = select_governor_rows(
                df_discourse_topics, governador_selecionado, universo_ativo
            )
            if df_discurso_filtrado.empty or "Name" not in df_discurso_filtrado.columns:
                st.info("Nenhum tópico de discurso para este governador ainda.")
            else:
                df_discurso_topicos = (
                    df_discurso_filtrado["Name"].value_counts().reset_index(name="count")
                )
                df_discurso_topicos.columns = ["Name", "count"]
                st.plotly_chart(
                    plot_top_n_bar(
                        df_discurso_topicos,
                        x="count",
                        y="Name",
                        title="Top tópicos do discurso oficial",
                    ),
                    width="stretch",
                )
    with col_reacao:
        st.markdown("##### Do que o público fala")
        if df_topicos is None:
            st.info(
                "Tópicos de comentário ainda não gerados para este "
                "governador -- ver seção 'Tópicos mais frequentes' acima."
            )
        else:
            st.plotly_chart(
                plot_top_n_bar(
                    df_topicos, x="count", y="Name", title="Top tópicos de comentário"
                ),
                width="stretch",
            )

    st.markdown(
        "#### Padrões de conteúdo (Reels e Feed)",
        help=(
            "Clusterização automática (AutoClusterHPO) por engajamento e "
            "duração/formato do post -- `content_type` discrimina Reels de "
            "posts do Feed (ADR 0020, Ficha 2)."
        ),
    )
    if df_clusters.empty:
        st.info(
            "`governor_clusters` ainda não existe. "
            "Rode `scripts/run_modeling.py` para gerá-la."
        )
    else:
        # Reels + posts do Feed juntos (mesma tabela `governor_clusters`,
        # discriminada por `content_type` -- ADR 0020, Ficha 2). Só `id`/
        # `inputUrl` importam aqui, o resto do join vem de `df_clusters`.
        partes_conteudo = [
            df[["id", "inputUrl"]]
            for df in (df_filtrado_reels, df_filtrado_posts)
            if not df.empty
        ]
        df_conteudo = (
            pd.concat(partes_conteudo, ignore_index=True)
            if partes_conteudo
            else pd.DataFrame(columns=["id", "inputUrl"])
        )
        df_conteudo_com_cluster = df_conteudo.merge(
            df_clusters, left_on="id", right_on="id_reel", how="inner"
        )
        if df_conteudo_com_cluster.empty:
            st.info("Nenhum post/reel deste governador tem cluster atribuído.")
        else:
            content_type_options = sorted(
                df_conteudo_com_cluster["content_type"].dropna().unique().tolist()
            )
            # Toggle opcional (spec: só relevante quando há mais de um
            # content_type pra filtrar -- com só "reel" disponível ainda
            # hoje, o toggle nem aparece, sem quebrar nada).
            content_type_filtro = "Todos"
            if len(content_type_options) > 1:
                content_type_filtro = st.radio(
                    "Filtrar por formato:",
                    options=["Todos"] + content_type_options,
                    horizontal=True,
                    key="insights_content_type_filtro",
                )
            df_exibir = df_conteudo_com_cluster
            if content_type_filtro != "Todos":
                df_exibir = df_exibir[df_exibir["content_type"] == content_type_filtro]
            st.dataframe(
                df_exibir.groupby(["content_type", "cluster_label"])
                .agg(qtd_posts=("id_reel", "nunique"), algoritmo=("cluster_algo", "first"))
                .reset_index()
            )

    st.markdown("#### Perfil de comportamento do governador")
    if profile_cluster_directory.empty:
        st.info(
            "`governor_profile_clusters_engagement` ainda não existe. "
            "Rode `scripts/run_profile_clustering_engagement.py` para gerá-la."
        )
    elif governador_selecionado == TODOS_GOVERNADORES:
        st.dataframe(
            governor_universe_filtrado.groupby("cluster_perfil_engajamento")
            .agg(qtd_governadores=("inputUrl", "nunique"))
            .reset_index()
        )
    else:
        linha = governor_universe_filtrado.loc[
            governor_universe_filtrado["inputUrl"] == governador_selecionado
        ]
        cluster_valor = linha["cluster_perfil_engajamento"].iloc[0] if not linha.empty else None
        if cluster_valor is None or pd.isna(cluster_valor):
            st.info("Este governador não tem cluster de perfil atribuído.")
        else:
            st.metric("Cluster de Perfil", int(cluster_valor))

# Para mostrar os dados brutos (opcional)
if st.checkbox("Mostrar dados brutos filtrados"):
    st.subheader("Dados Brutos")
    st.write(df_filtrado_comments)
