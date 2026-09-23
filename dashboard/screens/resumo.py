"""Tela 1 -- "Resumo da semana" (ADR 0021 / issue #111).

Home do novo dashboard: substitui o `app.py` antigo (raiz) e
`pages/01_explorar.py`. Estrutura fixa (ver ADR 0021, Princípio de design):
cabeçalho (governador + filtro de calendário) -> frase de decisão semafórica
-> 4 KPIs com variação -> 4 destaques -> rodapé.

ADR 0024 substituiu o antigo gráfico de tendência "por coleta" (rodapé) por
um 4º destaque curto ("Publicações recentes", contagem por data de
publicação) que aponta pra evidência completa na Tela 2 ("O que produzir") --
o filtro de calendário que antes vivia dentro do destaque de negatividade
subiu pro cabeçalho, no lugar do antigo seletor "Período".

Toda a lógica de decisão (nível do semáforo, seleção dos 4 destaques) vive em
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
from dashboard.core.deltas import (
    JANELA_ALERTA_NEGATIVIDADE_DIAS,
    LIMIAR_NEGATIVIDADE_ALERTA,
    compare_publication_window,
    compare_vs_historical_average,
    deduplicate_by_first_seen,
    filter_by_date_range,
    normalize_date_input_range,
    parse_publication_dates,
)

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
    if (
        negatividade_atual is not None
        and not pd.isna(negatividade_atual)
        and negatividade_atual >= limiar
    ):
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


# ---------------------------------------------------------------------------
# Deltas dos KPIs (ADR 0025 / issue #153): duas famílias de comparação --
# CONTEÚDO (% positivo, tem data de publicação real por comentário) compara
# por janela móvel; PERFIL (% engajamento, Seguidores, NSM -- só um valor
# observado por execução) compara vs. média histórica. Ver docstring de
# `dashboard/core/deltas.py` para a justificativa completa.
# ---------------------------------------------------------------------------


def _delta_janela_publicacao_para_governador(
    df_sentiment_history_governador: pd.DataFrame,
) -> tuple[object, float | None, float | None] | None:
    """`(valor_atual, delta_percentual, valor_anterior)` de `% positivo`
    para o governador já filtrado, via `deltas.compare_publication_window`
    (janela atual de `deltas.JANELA_ALERTA_NEGATIVIDADE_DIAS` dias por data
    de publicação do comentário vs. a janela anterior) -- ADR 0025, substitui
    a comparação por execução (`week_over_week`) usada antes desta ADR.
    `None` se não houver dado suficiente -- chamador trata como "sem seta de
    variação", nunca como erro."""
    if (
        df_sentiment_history_governador.empty
        or "sentiment_label" not in df_sentiment_history_governador.columns
    ):
        return None
    df = df_sentiment_history_governador.assign(
        _is_positive=(df_sentiment_history_governador["sentiment_label"] == "positive").astype(
            float
        )
    )
    resultado = compare_publication_window(df, value_col="_is_positive", key_col=None)
    if resultado is None:
        return None
    return resultado.get(None)


def _delta_vs_media_historica_para_governador(
    df_history: pd.DataFrame,
    value_col: str,
    governor_url: str,
    key_col: str = "_chave",
    run_col: str = "_run_id",
) -> tuple[object, float | None] | None:
    """`(valor_atual, delta_percentual)` de `value_col` (métrica de PERFIL:
    % engajamento, Seguidores, NSM) para `governor_url`, via
    `deltas.compare_vs_historical_average` (ADR 0025) -- substitui
    `week_over_week`/"vs. última coleta" para essas 3 métricas, resiliente a
    qualquer espaçamento real entre execuções. `None` se não houver
    histórico suficiente ou se `governor_url` não aparecer no histórico --
    chamador trata `None` como "sem seta de variação", nunca como erro."""
    if df_history.empty or key_col not in df_history.columns:
        return None
    resultado = compare_vs_historical_average(
        df_history, value_col=value_col, key_col=key_col, run_col=run_col
    )
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


def _maior_alta_negatividade(
    df_sentiment_history: pd.DataFrame,
    data_inicio: object | None = None,
    data_fim: object | None = None,
) -> dict | None:
    """Tópico de comentário (`Topic`/`Name`) com maior `% negativo` agregado
    no intervalo `[data_inicio, data_fim]` de datas de PUBLICAÇÃO (ADR 0023).

    MUDANÇA DE SEMÂNTICA (substitui o critério anterior desta função, issue
    #111): antes comparava as 2 execuções mais recentes ("maior aumento
    entre atual e anterior"); agora não existe mais essa noção de "atual vs.
    anterior" quando o eixo passa a ser a data real de publicação do
    comentário -- o comentário mais antigo e o mais novo do período filtrado
    podem ter vindo da mesma execução, ou de execuções bem diferentes. O
    critério vira simplesmente "qual tópico concentrou mais negatividade no
    período escolhido pela analista" -- `data_inicio`/`data_fim` `None`
    (default) usa todo o histórico disponível.

    IMPORTANTE: `df_sentiment_history` deve chegar aqui já filtrado ao
    governador selecionado (ver `render()`, `_filtrar_por_governador`) -- esta
    função não faz nenhum filtro por `inputUrl` sozinha. Passar o histórico
    de todos os 27 perfis produz o tópico com mais negatividade entre todos
    os governadores combinados, não o do perfil que a analista está olhando
    (contrariaria a user story 1 da tela: "escolher o governador... para ver
    o resumo do perfil que acompanho").

    Deduplica por `id_comment`/menor `_run_id` antes de agregar (ver
    `dashboard.core.deltas.deduplicate_by_first_seen`) -- evita contar duas
    vezes um comentário recoletado em execuções sobrepostas.

    `None` se não houver dado suficiente (nenhum tópico atribuído -- BERTopic
    não rodou --, nenhum comentário no intervalo filtrado, ou nenhum tópico
    com negatividade > 0) -- não força um "destaque" artificial quando o
    período foi estável ou positivo em todos os tópicos."""
    required = {"Topic", "Name", "sentiment_label", "timestamp", "id_comment", "_run_id"}
    if df_sentiment_history.empty or not required.issubset(df_sentiment_history.columns):
        return None

    df = df_sentiment_history.dropna(subset=["Topic"])
    if df.empty:
        return None

    df = deduplicate_by_first_seen(df)
    df = df.assign(_data_publicacao=parse_publication_dates(df)).dropna(subset=["_data_publicacao"])
    df = filter_by_date_range(df, "_data_publicacao", data_inicio, data_fim)
    if df.empty:
        return None

    agregado = (
        df.groupby(["Topic", "Name"])["sentiment_label"]
        .apply(lambda s: (s == "negative").mean())
        .rename("pct_negativo")
        .reset_index()
    )
    candidatos = agregado[agregado["pct_negativo"] > 0]
    if candidatos.empty:
        return None

    linha = candidatos.sort_values("pct_negativo", ascending=False).iloc[0]
    return {
        "topic": linha["Topic"],
        "name": linha["Name"],
        "pct_negativo": linha["pct_negativo"] * 100,
    }


def _intervalo_disponivel(
    df: pd.DataFrame, timestamp_col: str = "timestamp"
) -> tuple[object, object] | None:
    """`(data_min, data_max)` de `timestamp_col` parseado em `df` -- limites
    default do filtro de calendário do destaque de negatividade (ADR 0023:
    abre com todo o período disponível, sem corte padrão). `None` se `df`
    estiver vazio, sem `timestamp_col`, ou sem nenhuma data parseável."""
    if df.empty or timestamp_col not in df.columns:
        return None
    datas = parse_publication_dates(df, timestamp_col=timestamp_col).dropna()
    if datas.empty:
        return None
    return datas.min(), datas.max()


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
# Destaque 4 -- quantidade de publicações recentes (ADR 0024)
# ---------------------------------------------------------------------------

_JANELA_DESTAQUE_PUBLICACOES_DIAS = 7


def _contagem_publicacoes_recentes(
    df_reels: pd.DataFrame, df_posts: pd.DataFrame, governor_url: str
) -> tuple[int, int] | None:
    """`(quantidade, janela_em_dias)` de publicações (reels + posts de feed,
    `data_hora`) do governador nos `_JANELA_DESTAQUE_PUBLICACOES_DIAS` dias
    mais recentes -- ADR 0024.

    A janela termina na data de publicação MAIS RECENTE disponível no dado
    (nunca `datetime.date.today()`): o pipeline não roda com cadência fixa
    (ADR 0021, ponto de atrito 4) -- ancorar em "hoje" faria uma lacuna de
    coleta parecer "o governador não postou nada" quando só significa "não
    coletamos recentemente".

    `None` (nunca `0` fabricado) se nenhuma das duas tabelas tiver
    publicação com `data_hora` parseável para este governador -- `render()`
    mostra uma mensagem amigável nesse caso, nunca um "0 publicações" que
    pareça um erro de cálculo."""
    partes = [
        _filtrar_por_governador(df, governor_url)
        for df in (df_reels, df_posts)
        if not df.empty and "data_hora" in df.columns
    ]
    partes = [p[["data_hora"]] for p in partes if not p.empty]
    if not partes:
        return None

    datas = pd.to_datetime(pd.concat(partes, ignore_index=True)["data_hora"], errors="coerce")
    datas = datas.dropna()
    if datas.empty:
        return None

    data_corte = datas.max() - pd.Timedelta(days=_JANELA_DESTAQUE_PUBLICACOES_DIAS)
    quantidade = int((datas > data_corte).sum())
    return quantidade, _JANELA_DESTAQUE_PUBLICACOES_DIAS


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

    # `df_sentiment_history_governador` precisa existir ANTES do cabeçalho
    # terminar de renderizar -- ADR 0024 move o filtro de calendário que
    # antes vivia só dentro do destaque 2 pra `header_col2`, e esse filtro
    # precisa da data mínima/máxima do histórico deste governador pra
    # calcular seus limites (`_intervalo_disponivel`).
    df_sentiment_history = data.comments_only(data.load_sentiment_history())
    df_sentiment_history_governador = (
        _filtrar_por_governador(df_sentiment_history, governor_url)
        if governor_url is not None
        else df_sentiment_history.iloc[0:0]
    )

    with header_col2:
        intervalo_disponivel = _intervalo_disponivel(df_sentiment_history_governador)
        if intervalo_disponivel is None:
            st.selectbox(
                "Período (tema em alta de negatividade)",
                options=[_PLACEHOLDER_SEM_GOVERNADOR],
                disabled=True,
                help=(
                    "Filtro de calendário do destaque \"tema em alta de "
                    "negatividade\" abaixo -- disponível quando houver "
                    "histórico de comentários deste governador."
                ),
            )
            data_inicio_negatividade, data_fim_negatividade = None, None
        else:
            data_min, data_max = intervalo_disponivel
            intervalo = st.date_input(
                "Período (tema em alta de negatividade)",
                value=(data_min, data_max),
                min_value=data_min,
                max_value=data_max,
                key="resumo_intervalo_tema_negatividade",
            )
            data_inicio_negatividade, data_fim_negatividade = normalize_date_input_range(
                intervalo
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
    df_engagement_history = data.load_engagement_history()
    if not df_engagement_history.empty and "inputUrl" in df_engagement_history.columns:
        df_engagement_history = df_engagement_history.assign(
            _chave=_normalize_url(df_engagement_history["inputUrl"])
        )
    df_nsm_history = data.load_nsm_history()
    if not df_nsm_history.empty and "inputUrl" in df_nsm_history.columns:
        df_nsm_history = df_nsm_history.assign(_chave=_normalize_url(df_nsm_history["inputUrl"]))
    # `df_sentiment_history_governador` (usado pelo destaque 2 e, desde a ADR
    # 0025, pelo delta de "% positivo" abaixo) já foi calculado antes do
    # cabeçalho, junto com o filtro de calendário que vive em `header_col2`
    # (ADR 0024) -- não recalcular aqui.
    df_nsm_governador = _filtrar_por_governador(data.load_nsm(), governor_url)

    prop_positivo_atual = _proporcao_label(df_sentiment_governador, "positive")
    prop_negativo_atual = _proporcao_label(df_sentiment_governador, "negative")

    # ADR 0025: % engajamento/Seguidores/NSM (métricas de PERFIL) comparam
    # vs. média histórica; % positivo (métrica de CONTEÚDO) compara por
    # janela de data de publicação -- ver docstring das duas funções acima.
    resultado_engajamento = _delta_vs_media_historica_para_governador(
        df_engagement_history, "% ENGAJAMENTO", governor_url
    )
    resultado_seguidores = _delta_vs_media_historica_para_governador(
        df_engagement_history, "followersCount", governor_url
    )
    resultado_nsm = _delta_vs_media_historica_para_governador(
        df_nsm_history, "nsm", governor_url
    )
    resultado_positivo = _delta_janela_publicacao_para_governador(
        df_sentiment_history_governador
    )

    delta_engajamento = resultado_engajamento[1] if resultado_engajamento else None
    delta_positivo = resultado_positivo[1] if resultado_positivo else None

    # ---- Frase de decisão ----
    nivel = _nivel_semaforo(delta_positivo, delta_engajamento, prop_negativo_atual)
    decision_band(_frase_decisao(nivel, delta_positivo, delta_engajamento), level=nivel)
    # ADR 0025: engajamento/seguidores/NSM não têm data de publicação por
    # linha (só `_run_id`/`_generated_at`) -- comparam vs. MÉDIA HISTÓRICA de
    # execuções, nunca "vs. última coleta". % positivo tem data de
    # publicação real por comentário -- compara por janela de
    # `deltas.JANELA_ALERTA_NEGATIVIDADE_DIAS` dias, independente do período
    # filtrado no destaque de negatividade abaixo (que é uma seleção livre
    # de intervalo, não a janela fixa da comparação).
    st.caption(
        "Engajamento, seguidores e NSM comparam contra a média histórica de "
        "execuções. % positivo compara os últimos "
        f"{JANELA_ALERTA_NEGATIVIDADE_DIAS} dias de publicação vs. os "
        f"{JANELA_ALERTA_NEGATIVIDADE_DIAS} dias anteriores -- ambos "
        "independentes do período filtrado no destaque de negatividade "
        "abaixo."
    )

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
                # ADR 0025 / issue #153: `load_nsm_history()` já existe
                # (espelha `load_engagement_history()`), mas a pipeline
                # ainda não escreve `governor_nsm_history` hoje
                # (`NsmScorer.write` grava `governor_nsm` em modo
                # `overwrite`, sem variante de histórico -- ver
                # `src/repositories/delta_repository.py::load_nsm_history`).
                # `resultado_nsm` degrada para `None` graciosamente até essa
                # mudança de pipeline (fora do escopo desta issue) acontecer
                # -- não é um esquecimento, é ausência real de dado.
                _fmt_delta_pct(resultado_nsm[1] if resultado_nsm else None),
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
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown("**Melhor post**")
        # `data.load_reels_content()` retorna TODOS os 27 perfis -- ambas as
        # funções abaixo (`_melhor_post`/`_contagem_publicacoes_recentes`)
        # filtram por `governor_url` internamente, nunca recebem dado
        # pré-filtrado daqui.
        df_reels_conteudo = data.load_reels_content()
        melhor = _melhor_post(data.load_clusters_content(), df_reels_conteudo, governor_url)
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
        # ADR 0023/0024: o filtro de calendário desta tela vive em
        # `header_col2` e afeta só este destaque -- por data real de
        # publicação do comentário, abrindo com todo o período disponível
        # (sem corte padrão). Ver `intervalo_disponivel`/
        # `data_inicio_negatividade`/`data_fim_negatividade`, computados no
        # cabeçalho.
        if intervalo_disponivel is None:
            st.caption("Sem histórico de sentimento suficiente para este destaque.")
        else:
            alta_negatividade = _maior_alta_negatividade(
                df_sentiment_history_governador, data_inicio_negatividade, data_fim_negatividade
            )
            if alta_negatividade is None:
                st.caption("Nenhum tema com negatividade no período selecionado.")
            else:
                st.write(
                    f"**{alta_negatividade['name']}** -- "
                    f"{alta_negatividade['pct_negativo']:.1f}% de negatividade no período."
                )
                st.caption("Ver mais na tela Radar de crise.")

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

    with col4:
        st.markdown("**Publicações recentes**")
        # ADR 0024: substitui o antigo gráfico de tendência "por coleta" do
        # rodapé -- contagem simples por data de publicação real, com
        # atalho pra evidência completa em "O que produzir".
        resultado_publicacoes = _contagem_publicacoes_recentes(
            df_reels_conteudo, data.load_posts_content(), governor_url
        )
        if resultado_publicacoes is None:
            st.caption("Sem publicação com data de conteúdo disponível ainda.")
        else:
            quantidade, janela_dias = resultado_publicacoes
            st.write(f"{quantidade} publicação(ões) nos últimos {janela_dias} dias")
            st.caption("Ver tendência completa na tela O que produzir.")

    footnote()
