"""Tela 1 -- "Resumo da semana" (ADR 0021 / issue #111).

Home do novo dashboard: substitui o `app.py` antigo (raiz) e
`pages/01_explorar.py`. Estrutura fixa (ver ADR 0021, Princípio de design):
cabeçalho (governador + período) -> frase de decisão semafórica -> 4 KPIs
com variação -> 3 destaques + gráfico de tendência -> rodapé.

Toda a lógica de decisão (nível do semáforo, seleção dos 3 destaques) vive em
funções puras nomeadas abaixo, testadas em
`tests/test_dashboard_screens_resumo.py` -- `render()` só orquestra I/O do
Streamlit sobre o resultado dessas funções, nunca calcula nada sozinho (ver
issue #111, Testing Decisions).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.core import data
from dashboard.core.components import decision_band, footnote, kpi_row, stage_label
from dashboard.core.deltas import LIMIAR_NEGATIVIDADE_ALERTA, week_over_week

_PLACEHOLDER_SEM_GOVERNADOR = "—"


# ---------------------------------------------------------------------------
# Normalização / seleção de governador
# ---------------------------------------------------------------------------


def _normalize_url(series: pd.Series) -> pd.Series:
    """Normaliza URL de perfil para join (remove espaço, query string,
    fragmento, barra final, caixa) -- mesma normalização que
    `src/dashboard/filters.py::_normalize_url` já precisou aplicar
    historicamente porque `governor_engagement`/`governor_sentiment`/
    `reels_clean` nem sempre gravam a mesma URL byte-a-byte igual. Duplicada
    aqui (função pequena, sem estado) em vez de importada de
    `src/dashboard/filters.py`, que está sendo descontinuado tela por tela
    pela ADR 0021 -- Tela 1 não deve criar uma nova dependência num módulo
    que vai desaparecer."""
    return (
        series.astype(str)
        .str.strip()
        .str.split("?", n=1)
        .str[0]
        .str.split("#", n=1)
        .str[0]
        .str.rstrip("/")
        .str.lower()
    )


def _governor_options(df_metadata: pd.DataFrame) -> dict[str, str]:
    """`{nome_de_exibição: inputUrl}`, ordenado por nome -- opções do
    `st.selectbox` de governador. Vazio (não lança exceção) se
    `governors_metadata` ainda não existir; `render()` degrada para as URLs
    brutas de `load_engagement()` nesse caso (ver `render()` abaixo)."""
    if df_metadata.empty or "inputUrl" not in df_metadata.columns:
        return {}
    col_nome = "nome" if "nome" in df_metadata.columns else "inputUrl"
    pares = (
        df_metadata[["inputUrl", col_nome]]
        .dropna(subset=["inputUrl"])
        .drop_duplicates(subset=["inputUrl"])
    )
    nomes = pares[col_nome].fillna(pares["inputUrl"])
    return dict(sorted(zip(nomes, pares["inputUrl"], strict=True), key=lambda kv: kv[0]))


def _filtrar_por_governador(
    df: pd.DataFrame, governor_url: str, url_col: str = "inputUrl"
) -> pd.DataFrame:
    """`df` filtrado às linhas cujo `url_col` normalizado bate com
    `governor_url` normalizado. `DataFrame` vazio (nunca exceção) se `df`
    estiver vazio ou não tiver `url_col`."""
    if df.empty or url_col not in df.columns:
        return df.iloc[0:0]
    chave = _normalize_url(pd.Series([governor_url])).iloc[0]
    return df[_normalize_url(df[url_col]) == chave]


# ---------------------------------------------------------------------------
# Formatação (arredondamento no ponto de exibição -- issue #111, user story 11)
# ---------------------------------------------------------------------------


def _fmt_pct(valor: float | None) -> str:
    """Fração (0-1) -> string de porcentagem com 1 casa decimal. Nunca exibe
    o float bruto (ex.: "71.428571%")."""
    if valor is None or pd.isna(valor):
        return _PLACEHOLDER_SEM_GOVERNADOR
    return f"{valor * 100:.1f}%"


def _fmt_delta_pct(delta: float | None) -> str | None:
    """Delta percentual (já em pontos percentuais de variação, ver
    `dashboard/core/deltas.week_over_week`) -> string com sinal, ou `None`
    para `st.metric` ocultar a seta (issue #111, user story 6)."""
    if delta is None or pd.isna(delta):
        return None
    return f"{delta:+.1f}%"


def _fmt_int_br(valor: float | None) -> str:
    """Inteiro com separador de milhar `.` (pt-BR) -- usado para seguidores."""
    if valor is None or pd.isna(valor):
        return _PLACEHOLDER_SEM_GOVERNADOR
    return f"{int(valor):,}".replace(",", ".")


def _fmt_nsm(valor: float | None) -> str:
    if valor is None or pd.isna(valor):
        return _PLACEHOLDER_SEM_GOVERNADOR
    return f"{valor:.2f}"


# ---------------------------------------------------------------------------
# Frase de decisão / nível do semáforo (issue #111, user story 3)
# ---------------------------------------------------------------------------


def _nivel_semaforo(
    delta_positivo: float | None,
    delta_engajamento: float | None,
    negatividade_atual: float | None,
    limiar: float = LIMIAR_NEGATIVIDADE_ALERTA,
) -> str:
    """Nível da faixa de decisão -- uma chave de `dashboard.core.theme.COLORS`
    (`"good"`/`"warn"`/`"danger"`/`"info"`).

    - `"danger"`: `negatividade_atual` cruzou `limiar` (mesmo critério que a
      Tela 3/Radar de crise, issue #113, deve reusar -- ver
      `dashboard/core/deltas.LIMIAR_NEGATIVIDADE_ALERTA`). Checado primeiro:
      uma crise de negatividade é o sinal mais urgente, independente de os
      dois deltas terem subido.
    - `"good"`: os dois deltas (`% positivo`, `% engajamento`) são positivos.
    - `"warn"`: pelo menos um dos dois deltas é negativo (o outro pode ser
      positivo, negativo ou ausente).
    - `"info"`: dado insuficiente para comparar (ex.: só 1 execução no
      histórico) -- nunca lança exceção, nunca finge uma cor de decisão sem
      base."""
    if negatividade_atual is not None and not pd.isna(negatividade_atual):
        if negatividade_atual >= limiar:
            return "danger"

    if delta_positivo is not None and delta_engajamento is not None:
        if delta_positivo > 0 and delta_engajamento > 0:
            return "good"
        if delta_positivo < 0 or delta_engajamento < 0:
            return "warn"

    return "info"


def _frase_decisao(
    nivel: str,
    delta_positivo: float | None,
    delta_engajamento: float | None,
) -> str:
    """Texto da faixa de decisão para cada nível de `_nivel_semaforo` --
    sempre a primeira coisa lida na tela (ver CONTEXT.md, "Frase de
    decisão")."""
    if nivel == "danger":
        return (
            "Atenção: a negatividade dos comentários cruzou o limite de alerta "
            "-- prioridade para a tela de Radar de crise assim que ela existir."
        )
    if nivel == "good":
        return "Boa semana: % positivo e % de engajamento subiram vs. a coleta anterior."
    if nivel == "warn":
        return (
            "Semana mista: % positivo ou % de engajamento caiu vs. a coleta "
            "anterior -- vale olhar com mais atenção."
        )
    return "Ainda não há coletas suficientes para comparar esta semana com a anterior."


# ---------------------------------------------------------------------------
# Proporções de sentimento (comentários)
# ---------------------------------------------------------------------------


def _proporcao_label(df_comments: pd.DataFrame, label: str) -> float | None:
    """Proporção de `sentiment_label == label` em `df_comments`. `None`
    (nunca `ZeroDivisionError`) se `df_comments` estiver vazio."""
    if df_comments.empty or "sentiment_label" not in df_comments.columns:
        return None
    total = len(df_comments)
    if total == 0:
        return None
    return (df_comments["sentiment_label"] == label).sum() / total


def _agregar_pct_positivo_por_run(df_sentiment_history: pd.DataFrame) -> pd.DataFrame:
    """1 linha por (`_chave`, `_run_id`): proporção de `sentiment_label ==
    'positive'` -- pré-agregação exigida porque `week_over_week` espera 1
    valor já pronto por chave por execução, não comentários individuais.
    `_chave` é `inputUrl` normalizado (ver `_normalize_url`)."""
    required = {"inputUrl", "sentiment_label", "_run_id"}
    if df_sentiment_history.empty or not required.issubset(df_sentiment_history.columns):
        return pd.DataFrame(columns=["_chave", "_run_id", "pct_positivo"])

    df = df_sentiment_history.assign(_chave=_normalize_url(df_sentiment_history["inputUrl"]))
    agregado = (
        df.groupby(["_chave", "_run_id"])["sentiment_label"]
        .apply(lambda s: (s == "positive").mean())
        .rename("pct_positivo")
        .reset_index()
    )
    return agregado


# ---------------------------------------------------------------------------
# Delta genérico contra histórico (engajamento/seguidores/% positivo)
# ---------------------------------------------------------------------------


def _delta_para_governador(
    df_history: pd.DataFrame,
    value_col: str,
    governor_url: str,
    key_col: str = "_chave",
    run_col: str = "_run_id",
) -> tuple[object, float | None] | None:
    """`(valor_atual, delta_percentual)` de `value_col` para `governor_url`,
    via `week_over_week`. `None` se não houver histórico suficiente (2+
    execuções) ou se `governor_url` não aparecer no histórico -- chamador
    trata `None` como "sem seta de variação", nunca como erro."""
    if df_history.empty or key_col not in df_history.columns:
        return None
    resultado = week_over_week(df_history, value_col=value_col, key_col=key_col, run_col=run_col)
    if resultado is None:
        return None
    chave = _normalize_url(pd.Series([governor_url])).iloc[0]
    return resultado.get(chave)


# ---------------------------------------------------------------------------
# Destaque 1 -- melhor post/reel da execução (issue #111, user story 7)
# ---------------------------------------------------------------------------


def _melhor_post(
    df_clusters: pd.DataFrame, df_reels: pd.DataFrame, governor_url: str
) -> dict | None:
    """Reel do governador (`content_type == 'reel'`) com maior `Total de
    Engajamento` na execução mais recente de `reels_clean`.

    `governor_clusters` (`df_clusters`) não grava nenhuma métrica de
    engajamento por post nem `inputUrl` (ver docstring de
    `dashboard.core.data.load_reels_content`) -- por isso este destaque cruza
    `df_clusters` com `reels_clean` (`df_reels`) por `id`/`id_reel`, mesmo
    join já usado em `src/dashboard/filters.py::build_cluster_membership`.
    `None` se qualquer uma das tabelas estiver vazia ou sem match -- nunca
    lança exceção."""
    if df_clusters.empty or df_reels.empty or not governor_url:
        return None
    if "content_type" not in df_clusters.columns or "id_reel" not in df_clusters.columns:
        return None

    clusters_reel = df_clusters[df_clusters["content_type"] == "reel"]
    if clusters_reel.empty:
        return None

    reels_governador = _filtrar_por_governador(df_reels, governor_url)
    if reels_governador.empty or "Total de Engajamento" not in reels_governador.columns:
        return None
    if "id" not in reels_governador.columns:
        return None

    merged = reels_governador.merge(clusters_reel, left_on="id", right_on="id_reel", how="inner")
    if merged.empty:
        return None

    linha = merged.sort_values("Total de Engajamento", ascending=False).iloc[0]
    return {
        "id": linha.get("id"),
        "shortCode": linha.get("shortCode"),
        "total_engajamento": linha["Total de Engajamento"],
    }


# ---------------------------------------------------------------------------
# Destaque 2 -- tema com maior alta de negatividade (issue #111, user story 7)
# ---------------------------------------------------------------------------


def _maior_alta_negatividade(df_sentiment_history: pd.DataFrame) -> dict | None:
    """Tópico de comentário (`Topic`/`Name`) com maior AUMENTO na proporção
    de `sentiment_label == 'negative'` entre as duas execuções mais recentes
    de `governor_sentiment_history` (já filtrado a `comments_only`).

    IMPORTANTE: `df_sentiment_history` deve chegar aqui já filtrado ao
    governador selecionado (ver `render()`, `_filtrar_por_governador`) -- esta
    função não faz nenhum filtro por `inputUrl` sozinha. Passar o histórico
    de todos os 27 perfis produz o tópico que mais piorou entre todos os
    governadores combinados, não o do perfil que a analista está olhando
    (contrariaria a user story 1 da tela: "escolher o governador... para ver
    o resumo do perfil que acompanho").

    `None` se não houver histórico suficiente, nenhum tópico atribuído
    (`Topic` sempre nulo -- BERTopic não rodou), ou se nenhum tópico tiver
    alta de negatividade (aumento <= 0) -- não força um "destaque" artificial
    quando a semana foi estável ou melhorou em todos os tópicos."""
    required = {"Topic", "Name", "sentiment_label", "_run_id"}
    if df_sentiment_history.empty or not required.issubset(df_sentiment_history.columns):
        return None

    df = df_sentiment_history.dropna(subset=["Topic"])
    if df.empty:
        return None

    runs = sorted(df["_run_id"].unique())
    if len(runs) < 2:
        return None
    atual_id, anterior_id = runs[-1], runs[-2]

    agregado = (
        df.groupby(["_run_id", "Topic", "Name"])["sentiment_label"]
        .apply(lambda s: (s == "negative").mean())
        .rename("pct_negativo")
        .reset_index()
    )
    atual = agregado[agregado["_run_id"] == atual_id].set_index("Topic")["pct_negativo"]
    anterior = agregado[agregado["_run_id"] == anterior_id].set_index("Topic")["pct_negativo"]

    comuns = atual.index.intersection(anterior.index)
    if comuns.empty:
        return None

    delta = (atual.loc[comuns] - anterior.loc[comuns]).sort_values(ascending=False)
    if delta.empty or delta.iloc[0] <= 0:
        return None

    topic_id = delta.index[0]
    nome = agregado.loc[
        (agregado["_run_id"] == atual_id) & (agregado["Topic"] == topic_id), "Name"
    ].iloc[0]
    return {
        "topic": topic_id,
        "name": nome,
        "delta_pct_negativo": delta.iloc[0] * 100,
    }


# ---------------------------------------------------------------------------
# Destaque 3 -- alto % positivo e baixo volume de discurso (user story 7)
# ---------------------------------------------------------------------------

SEM_DADO_DISCURSO = "sem_dado_discurso"
"""Sentinela retornada por `_topico_alto_positivo_baixo_discurso` quando
`load_discourse_topics()` vier vazia -- distinta de `None` (que também pode
significar "sem tópico prioritário calculável") para que `render()` mostre a
mensagem amigável específica pedida pela issue #111 ("dado de discurso ainda
não disponível") em vez de um estado vazio genérico."""


def _topico_alto_positivo_baixo_discurso(
    df_topic_priority: pd.DataFrame, df_discourse_topics: pd.DataFrame
) -> dict | str | None:
    """Tópico de comentário com `proporcao_sentimento_positivo` acima da
    mediana E menor volume de menções no discurso oficial
    (`governor_discourse_topics`) -- "falamos pouco sobre algo que o público
    recebe bem".

    Retorna `SEM_DADO_DISCURSO` (não `None`) se `df_discourse_topics` vier
    vazia -- degrada para uma mensagem amigável em vez de quebrar (issue
    #111, Testing Decisions). Retorna `None` só quando não há tópico
    prioritário calculável mesmo com as duas tabelas presentes."""
    if df_topic_priority.empty or "proporcao_sentimento_positivo" not in df_topic_priority.columns:
        return None
    if df_discourse_topics.empty:
        return SEM_DADO_DISCURSO
    if "Topic" not in df_discourse_topics.columns:
        return SEM_DADO_DISCURSO

    volume = (
        df_discourse_topics.dropna(subset=["Topic"])
        .groupby("Topic")
        .size()
        .rename("volume_discurso")
        .reset_index()
    )
    merged = df_topic_priority.merge(volume, on="Topic", how="left")
    merged["volume_discurso"] = merged["volume_discurso"].fillna(0)

    limiar_positivo = merged["proporcao_sentimento_positivo"].median()
    candidatos = merged[merged["proporcao_sentimento_positivo"] >= limiar_positivo]
    if candidatos.empty:
        return None

    linha = candidatos.sort_values("volume_discurso", ascending=True).iloc[0]
    return {
        "topic": linha["Topic"],
        "name": linha.get("Name"),
        "proporcao_positivo": linha["proporcao_sentimento_positivo"],
        "volume_discurso": linha["volume_discurso"],
    }


# ---------------------------------------------------------------------------
# Gráfico de tendência (últimas ~4 execuções)
# ---------------------------------------------------------------------------


def _ultimas_execucoes(
    df_history: pd.DataFrame, governor_url: str, value_col: str, n: int = 4
) -> pd.DataFrame:
    """Últimas `n` execuções de `df_history` para `governor_url`, ordenadas
    da mais antiga para a mais recente (ordem certa para um gráfico de
    barras de tendência) -- `DataFrame` vazio se não houver dado."""
    df_governador = _filtrar_por_governador(df_history, governor_url)
    if df_governador.empty or value_col not in df_governador.columns:
        return pd.DataFrame(columns=["_run_id", value_col])

    ordenar_por = "_generated_at" if "_generated_at" in df_governador.columns else "_run_id"
    df_ordenado = df_governador.sort_values(ordenar_por)
    return df_ordenado[["_run_id", value_col]].tail(n).reset_index(drop=True)


# ---------------------------------------------------------------------------
# render()
# ---------------------------------------------------------------------------


def render() -> None:
    df_metadata = data.load_governors_metadata()
    df_engagement = data.load_engagement()

    options = _governor_options(df_metadata)
    if not options and not df_engagement.empty and "inputUrl" in df_engagement.columns:
        # `governors_metadata` ainda não existe -- cai para URL bruta em vez
        # de travar a tela (mesmo padrão de degradação de
        # `src/dashboard/filters.py::render_governor_selector`).
        urls = df_engagement["inputUrl"].dropna().unique().tolist()
        options = {url: url for url in urls}

    header_col1, header_col2 = st.columns([2, 1])
    with header_col1:
        if not options:
            st.selectbox("Governador", options=[_PLACEHOLDER_SEM_GOVERNADOR], disabled=True)
            governor_url = None
        else:
            nome_selecionado = st.selectbox("Governador", options=list(options.keys()))
            governor_url = options[nome_selecionado]
    with header_col2:
        st.selectbox(
            "Período",
            options=["Última coleta"],
            help=(
                "A comparação numérica é sempre entre as duas execuções mais "
                "recentes -- o pipeline ainda não tem agendamento fixo "
                "(ver ADR 0021)."
            ),
        )
    stage_label("Visão do funil inteiro")

    if governor_url is None:
        st.info(
            "Nenhum governador disponível ainda -- rode a pipeline "
            "(`uv run python pipeline.py`) para popular o dashboard."
        )
        footnote()
        return

    # ---- Dado bruto ----
    df_sentiment_governador = _filtrar_por_governador(
        data.comments_only(data.load_sentiment()), governor_url
    )
    df_sentiment_history = data.comments_only(data.load_sentiment_history())
    df_engagement_history = data.load_engagement_history()
    if not df_engagement_history.empty and "inputUrl" in df_engagement_history.columns:
        df_engagement_history = df_engagement_history.assign(
            _chave=_normalize_url(df_engagement_history["inputUrl"])
        )
    df_pct_positivo_run = _agregar_pct_positivo_por_run(df_sentiment_history)
    # Destaque 2 (tema em alta de negatividade) precisa do histórico já
    # filtrado a ESTE governador -- sem isso, `_maior_alta_negatividade`
    # rankeia tópicos misturando os 27 perfis, contrariando a premissa da
    # tela (user story 1: "escolher o governador... para ver o resumo do
    # perfil que acompanho"). Mesmo escopo por governador que `% positivo`
    # já aplica via `_chave` em `_agregar_pct_positivo_por_run`.
    df_sentiment_history_governador = _filtrar_por_governador(df_sentiment_history, governor_url)
    df_nsm_governador = _filtrar_por_governador(data.load_nsm(), governor_url)

    prop_positivo_atual = _proporcao_label(df_sentiment_governador, "positive")
    prop_negativo_atual = _proporcao_label(df_sentiment_governador, "negative")

    resultado_engajamento = _delta_para_governador(
        df_engagement_history, "% ENGAJAMENTO", governor_url
    )
    resultado_seguidores = _delta_para_governador(
        df_engagement_history, "followersCount", governor_url
    )
    resultado_positivo = _delta_para_governador(df_pct_positivo_run, "pct_positivo", governor_url)

    delta_engajamento = resultado_engajamento[1] if resultado_engajamento else None
    delta_positivo = resultado_positivo[1] if resultado_positivo else None

    # ---- Frase de decisão ----
    nivel = _nivel_semaforo(delta_positivo, delta_engajamento, prop_negativo_atual)
    decision_band(_frase_decisao(nivel, delta_positivo, delta_engajamento), level=nivel)

    # ---- KPIs ----
    df_governador_engagement = _filtrar_por_governador(df_engagement, governor_url)
    valor_engajamento = (
        df_governador_engagement["% ENGAJAMENTO"].iloc[0]
        if not df_governador_engagement.empty and "% ENGAJAMENTO" in df_governador_engagement
        else None
    )
    valor_seguidores = (
        df_governador_engagement["followersCount"].iloc[0]
        if not df_governador_engagement.empty and "followersCount" in df_governador_engagement
        else None
    )
    valor_nsm = (
        df_nsm_governador["nsm"].iloc[0]
        if not df_nsm_governador.empty and "nsm" in df_nsm_governador.columns
        else None
    )

    kpi_row(
        [
            (
                "Engajamento qualificado · em validação",
                _fmt_nsm(valor_nsm),
                # `delta=None` sempre: não existe `load_nsm_history()` (fora
                # do escopo de `dashboard/core/data.py`, issue #110) -- sem
                # histórico, não há como chamar `week_over_week` para este
                # KPI. Não é um esquecimento; é ausência real de dado.
                None,
                None,
                (
                    "North Star Metric (NSM): comentários positivos sobre "
                    "comentários totais, ponderado pelo alcance estimado por "
                    "engajamento. Ainda em validação contra os 27 perfis "
                    "reais -- não confiar cegamente neste número."
                ),
            ),
            (
                "% engajamento",
                _fmt_pct(valor_engajamento),
                _fmt_delta_pct(delta_engajamento),
                None,
            ),
            (
                "% positivo",
                _fmt_pct(prop_positivo_atual),
                _fmt_delta_pct(delta_positivo),
                None,
                "Proporção de comentários positivos sobre o total avaliado.",
            ),
            (
                "Seguidores",
                _fmt_int_br(valor_seguidores),
                _fmt_delta_pct(resultado_seguidores[1] if resultado_seguidores else None),
                None,
            ),
        ]
    )

    # ---- Destaques ----
    st.markdown("#### Destaques da execução")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Melhor post**")
        melhor = _melhor_post(data.load_clusters_content(), data.load_reels_content(), governor_url)
        if melhor is None:
            st.caption("Sem reel com dado de engajamento suficiente nesta execução.")
        else:
            shortcode, id_reel = melhor["shortCode"], melhor["id"]
            if pd.notna(shortcode):
                identificador = shortcode
            elif pd.notna(id_reel):
                identificador = id_reel
            else:
                identificador = _PLACEHOLDER_SEM_GOVERNADOR
            st.write(f"`{identificador}` -- {_fmt_int_br(melhor['total_engajamento'])} de engajamento")

    with col2:
        st.markdown("**Tema em alta de negatividade**")
        alta_negatividade = _maior_alta_negatividade(df_sentiment_history_governador)
        if alta_negatividade is None:
            st.caption("Nenhum tema com alta de negatividade nas duas últimas execuções.")
        else:
            st.write(
                f"**{alta_negatividade['name']}** -- negatividade subiu "
                f"{alta_negatividade['delta_pct_negativo']:.1f} p.p."
            )
            st.caption("Ver mais na tela Radar de crise (em construção).")

    with col3:
        st.markdown("**Alto potencial, pouco discurso**")
        topico = _topico_alto_positivo_baixo_discurso(
            data.load_topic_priority(), data.load_discourse_topics()
        )
        if topico == SEM_DADO_DISCURSO:
            st.caption("Dado de discurso ainda não disponível.")
        elif topico is None:
            st.caption("Sem tópico prioritário identificável nesta execução.")
        else:
            st.write(
                f"**{topico['name']}** -- {_fmt_pct(topico['proporcao_positivo'])} positivo, "
                f"{int(topico['volume_discurso'])} menção(ões) no discurso oficial."
            )
            st.caption("Ver mais na tela O que produzir (em construção).")

    # ---- Tendência ----
    st.markdown("#### Tendência de engajamento (últimas execuções)")
    df_tendencia = _ultimas_execucoes(df_engagement_history, governor_url, "% ENGAJAMENTO")
    if df_tendencia.empty:
        st.caption("Sem histórico suficiente para mostrar uma tendência ainda.")
    else:
        df_grafico = df_tendencia.copy()
        df_grafico["% engajamento"] = df_grafico["% ENGAJAMENTO"] * 100
        st.bar_chart(df_grafico.set_index("_run_id")["% engajamento"])

    footnote()
