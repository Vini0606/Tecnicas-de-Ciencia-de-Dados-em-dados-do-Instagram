"""Tela 2 -- "O que produzir" (ADR 0021 / issue #112).

Responde "o que eu posto a seguir?" combinando duas fontes que hoje vivem
espalhadas em páginas técnicas (`pages/02_insights.py`, seção Score ICE, e
`pages/03_performance.py`, clusters de conteúdo): uma fila de temas
priorizados (`topic_priority_score`) e três cartões de formato de Reel
(`governor_clusters`), mais uma recomendação principal cruzando as duas.

Mesma estrutura fixa da Tela 1 (ver `dashboard/screens/resumo.py`, ADR 0021 --
Princípio de design): cabeçalho (governador) -> `stage_label` -> frase de
decisão -> prova (fila + cartões) -> rodapé. Toda a lógica de decisão vive em
funções puras nomeadas abaixo, testadas em
`tests/test_dashboard_screens_produzir.py` -- `render()` só orquestra I/O do
Streamlit sobre o resultado dessas funções, nunca calcula nada sozinho (mesmo
padrão da Tela 1).

Ambiguidade de spec resolvida nesta issue (ver PR): `topic_priority_score`
NÃO tem `inputUrl` -- é um ranking GLOBAL de tópicos de comentário sobre os
27 perfis combinados (ver `src/features/gold/topic_priority_scorer.py`,
`TopicPriorityScorer.score`, que agrupa só por `Topic`/`Name`, nunca por
perfil). "Filtrado ao governador selecionado" (issue #112, Implementation
Decisions) só pode significar: restringir a fila aos tópicos que aparecem
nos PRÓPRIOS comentários deste governador (`governor_sentiment`, fonte
"comentario", já filtrado por `inputUrl`) -- não recalcular o score por
perfil (fora de escopo, ver issue #112, Out of Scope: "não mudar a fórmula
do Score ICE"). O selo de prioridade (tercis) continua calculado sobre o
ranking GLOBAL (não só os tópicos deste governador) para não oscilar
artificialmente quando o governador selecionado tem poucos tópicos próprios
-- ver `_cortes_tercis`.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.core import data
from dashboard.core.components import decision_band, footnote, stage_label

_PLACEHOLDER_SEM_GOVERNADOR = "—"

# Rótulos de negócio dos 3 cartões de formato (ver CONTEXT.md, "Grupo de
# desempenho") -- únicas strings usadas para identificar um grupo de cluster
# em qualquer lugar renderizado; o `cluster_label` numérico bruto (incluindo
# "-1" do ruído do DBSCAN) nunca aparece em nenhuma string retornada por
# nenhuma função deste módulo.
GRUPO_CURTO = "curto, converte"
GRUPO_LONGO = "longo, ignorado"
GRUPO_VIRAL = "viral, debatido"
_ORDEM_CARTOES = [GRUPO_CURTO, GRUPO_LONGO, GRUPO_VIRAL]

SELO_ALTA = "Alta"
SELO_MEDIA = "Média"
SELO_CUIDADO = "Cuidado"


# ---------------------------------------------------------------------------
# Normalização / seleção de governador (duplicado de `resumo.py` -- mesmo
# raciocínio: cada tela fica autocontida, sem depender de outra tela nem de
# `src/dashboard/filters.py`, que está sendo descontinuado tela por tela).
# ---------------------------------------------------------------------------


def _normalize_url(series: pd.Series) -> pd.Series:
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
    if df.empty or url_col not in df.columns:
        return df.iloc[0:0]
    chave = _normalize_url(pd.Series([governor_url])).iloc[0]
    return df[_normalize_url(df[url_col]) == chave]


# ---------------------------------------------------------------------------
# Formatação (arredondamento no ponto de exibição -- issue #112, user story 8)
# ---------------------------------------------------------------------------


def _fmt_pct(valor: float | None) -> str:
    if valor is None or pd.isna(valor):
        return _PLACEHOLDER_SEM_GOVERNADOR
    return f"{valor * 100:.1f}%"


def _fmt_int_br(valor: float | None) -> str:
    if valor is None or pd.isna(valor):
        return _PLACEHOLDER_SEM_GOVERNADOR
    return f"{int(round(valor)):,}".replace(",", ".")


# ---------------------------------------------------------------------------
# Fila de prioridade (Score ICE -> selo, nunca o score bruto)
# ---------------------------------------------------------------------------

_COLUNAS_FILA = ["Topic", "Name", "score", "proporcao_sentimento_positivo", "Prioridade"]


def _cortes_tercis(df_topic_priority: pd.DataFrame) -> tuple[float, float]:
    """`(corte_alta, corte_media)` -- os 2 cortes de tercil do `score` ICE
    sobre TODO `topic_priority_score` (ranking global, não só os tópicos do
    governador selecionado -- ver docstring do módulo). `(0.0, 0.0)` se a
    tabela estiver vazia ou sem `score` -- nunca lança exceção; o chamador
    nunca usa este resultado quando não há linha nenhuma para classificar."""
    if df_topic_priority.empty or "score" not in df_topic_priority.columns:
        return (0.0, 0.0)
    scores = df_topic_priority["score"].dropna()
    if scores.empty:
        return (0.0, 0.0)
    return (float(scores.quantile(2 / 3)), float(scores.quantile(1 / 3)))


def _selo_prioridade(score: float | None, corte_alta: float, corte_media: float) -> str:
    """Selo de prioridade determinístico a partir do `score` ICE bruto e dos
    2 cortes de tercil (ver `_cortes_tercis`) -- nunca exibe o score em si
    (issue #112, Implementation Decisions: "nunca a coluna de score bruto").
    Cortes inclusivos do lado alto: `score == corte` entra na banda melhor."""
    if score is None or pd.isna(score):
        return SELO_CUIDADO
    if score >= corte_alta:
        return SELO_ALTA
    if score >= corte_media:
        return SELO_MEDIA
    return SELO_CUIDADO


def _topicos_do_governador(df_sentiment_governador: pd.DataFrame) -> set:
    """`Topic`s distintos presentes nos comentários do governador
    selecionado (já filtrado por `_filtrar_por_governador` +
    `data.comments_only`) -- usado para restringir o ranking GLOBAL de
    `topic_priority_score` aos temas que este governador realmente recebe
    comentário (ver docstring do módulo). Conjunto vazio (nunca exceção) se
    `df_sentiment_governador` estiver vazio ou sem `Topic`."""
    if df_sentiment_governador.empty or "Topic" not in df_sentiment_governador.columns:
        return set()
    return set(df_sentiment_governador["Topic"].dropna().unique())


def _fila_prioridade(df_topic_priority: pd.DataFrame, topicos_governador: set) -> pd.DataFrame:
    """Fila de temas priorizados deste governador: `topic_priority_score`
    restrito a `topicos_governador`, ordenado por `score` ICE decrescente,
    com o selo de prioridade já calculado. `DataFrame` vazio (colunas
    `_COLUNAS_FILA`, nunca exceção) se `df_topic_priority` estiver vazia ou
    se o governador não tiver nenhum tópico próprio -- `render()` mostra um
    estado vazio amigável nesse caso (issue #112, user story 7).

    Mantém `Topic`/`score` como colunas internas (não removidas aqui) para
    `_topico_prioritario_ajustado`/testes -- `render()` é responsável por
    exibir só `Name`/`% positivo`/`Prioridade` ao usuário final, nunca o
    score bruto."""
    required = {"Topic", "score", "proporcao_sentimento_positivo"}
    if df_topic_priority.empty or not required.issubset(df_topic_priority.columns):
        return pd.DataFrame(columns=_COLUNAS_FILA)
    if not topicos_governador:
        return pd.DataFrame(columns=_COLUNAS_FILA)

    df = df_topic_priority[df_topic_priority["Topic"].isin(topicos_governador)]
    if df.empty:
        return pd.DataFrame(columns=_COLUNAS_FILA)

    corte_alta, corte_media = _cortes_tercis(df_topic_priority)
    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    df = df.assign(
        Prioridade=df["score"].apply(lambda s: _selo_prioridade(s, corte_alta, corte_media))
    )
    return df[_COLUNAS_FILA]


# ---------------------------------------------------------------------------
# Cartões de formato (cluster_label -> grupo de negócio)
# ---------------------------------------------------------------------------


def _clusters_reel_do_governador(
    df_clusters: pd.DataFrame, df_reels: pd.DataFrame, governor_url: str
) -> pd.DataFrame:
    """Reels do governador (`content_type == 'reel'`) com `cluster_label`,
    `Total de Engajamento` e `videoDuration` juntos numa linha -- mesmo join
    `id`/`id_reel` de `governor_clusters` com `reels_clean` já usado em
    `resumo.py::_melhor_post` (ver docstring de `data.load_reels_content`:
    `governor_clusters` sozinha não tem `inputUrl` nem métrica de
    engajamento por post). `DataFrame` vazio (nunca exceção) se qualquer
    tabela estiver vazia, sem match, ou sem as colunas esperadas."""
    if df_clusters.empty or df_reels.empty or not governor_url:
        return pd.DataFrame()
    if "content_type" not in df_clusters.columns or "id_reel" not in df_clusters.columns:
        return pd.DataFrame()

    clusters_reel = df_clusters[df_clusters["content_type"] == "reel"]
    if clusters_reel.empty:
        return pd.DataFrame()

    reels_governador = _filtrar_por_governador(df_reels, governor_url)
    if reels_governador.empty or "id" not in reels_governador.columns:
        return pd.DataFrame()

    return reels_governador.merge(clusters_reel, left_on="id", right_on="id_reel", how="inner")


def _estatisticas_por_grupo(df_clusters_reel_governador: pd.DataFrame) -> pd.DataFrame:
    """1 linha por `cluster_label` (incluindo -1 = ruído): `n`,
    `engajamento_medio`, `engajamento_var` (variância amostral, 0.0 quando
    `n < 2` -- sem sinal de variância com 1 só reel) e `duracao_media`
    (`NaN` se `videoDuration` não existir/estiver sempre nula). `DataFrame`
    vazio se a entrada estiver vazia ou sem `cluster_label`/`Total de
    Engajamento`."""
    required = {"cluster_label", "Total de Engajamento"}
    colunas = ["cluster_label", "n", "engajamento_medio", "engajamento_var", "duracao_media"]
    if df_clusters_reel_governador.empty or not required.issubset(
        df_clusters_reel_governador.columns
    ):
        return pd.DataFrame(columns=colunas)

    df = df_clusters_reel_governador.copy()
    if "videoDuration" not in df.columns:
        df["videoDuration"] = pd.NA

    agregado = (
        df.groupby("cluster_label")
        .agg(
            n=("cluster_label", "size"),
            engajamento_medio=("Total de Engajamento", "mean"),
            engajamento_var=("Total de Engajamento", "var"),
            duracao_media=("videoDuration", "mean"),
        )
        .reset_index()
    )
    agregado["engajamento_var"] = agregado["engajamento_var"].fillna(0.0)
    return agregado


def _combinar_grupo(linhas: pd.DataFrame) -> dict:
    """Combina 1+ linhas de `_estatisticas_por_grupo` num único resumo
    (`n` total, `engajamento_medio` ponderado por `n`) -- usado tanto para
    juntar ruído a um grupo puro quanto para juntar vários grupos puros
    "sobrando" no mesmo cartão "curto, converte" (ver
    `_mapear_grupos_para_cartoes`, caso de 4+ grupos puros)."""
    n_total = int(linhas["n"].sum()) if not linhas.empty else 0
    if n_total <= 0:
        return {"n": 0, "engajamento_medio": 0.0}
    engajamento_medio = float((linhas["engajamento_medio"] * linhas["n"]).sum() / n_total)
    return {"n": n_total, "engajamento_medio": engajamento_medio}


def _mapear_grupos_para_cartoes(estatisticas: pd.DataFrame) -> dict[str, dict]:
    """Mapeia `cluster_label` -> um dos 3 grupos de negócio (`GRUPO_CURTO`/
    `GRUPO_LONGO`/`GRUPO_VIRAL`, ver CONTEXT.md "Grupo de desempenho").
    `estatisticas` é a saída de `_estatisticas_por_grupo` (1 linha por
    `cluster_label`, incluindo -1 = ruído do DBSCAN).

    Baseline assumido pela issue #112 (Implementation Decisions): 3 grupos
    "puros" (`cluster_label != -1`) + ruído. Quando `AutoClusterHPO`
    converge para um número diferente de grupos puros, esta função adapta
    (documentado no PR, issue #112 pede explicitamente para não assumir
    sempre 3 grupos puros):

    - 0 grupos puros, sem ruído: `{}` (nenhum cartão -- `render()` mostra o
      estado vazio).
    - 0 grupos puros, só ruído: o próprio ruído vira sozinho o cartão
      "viral, debatido" (ainda é a rotulagem de negócio correta para "casos
      atípicos" -- ver CONTEXT.md -- nunca um cartão de um 4º grupo cru).
    - 1 grupo puro: não há base de comparação para eleger um grupo "longo"
      -- o único grupo puro absorve o ruído e vira "viral, debatido"
      sozinho; "curto, converte" e "longo, ignorado" não aparecem.
    - 2 grupos puros: o de maior `duracao_media` vira "longo, ignorado"; o
      outro absorve o ruído e vira "viral, debatido"; "curto, converte" não
      aparece (não sobra um 3º grupo puro para ele).
    - 3 grupos puros (baseline da especificação): maior `duracao_media` ->
      "longo, ignorado"; entre os 2 restantes, o de maior
      `engajamento_var` (empate quebrado por `engajamento_medio`) absorve o
      ruído -> "viral, debatido"; o que sobra -> "curto, converte".
    - 4+ grupos puros: mesma regra do caso de 3 -- "longo" e "viral" elegem
      1 grupo puro cada; TODOS os demais grupos puros restantes são
      combinados num único cartão "curto, converte" (`_combinar_grupo`), em
      vez de inventar um 4º cartão.

    Nunca inclui o `cluster_label` numérico (incluindo -1) em nenhuma
    string retornada -- as chaves do dicionário são sempre um dos 3 rótulos
    de negócio fixos acima."""
    if estatisticas.empty or "cluster_label" not in estatisticas.columns:
        return {}

    ruido = estatisticas[estatisticas["cluster_label"] == -1]
    puros = estatisticas[estatisticas["cluster_label"] != -1].copy()

    if puros.empty:
        if ruido.empty:
            return {}
        return {GRUPO_VIRAL: _combinar_grupo(ruido)}

    if len(puros) == 1:
        return {GRUPO_VIRAL: _combinar_grupo(pd.concat([puros, ruido], ignore_index=True))}

    puros_por_duracao = puros.sort_values("duracao_media", ascending=False, na_position="last")
    label_longo = puros_por_duracao.iloc[0]["cluster_label"]
    restantes = puros[puros["cluster_label"] != label_longo]

    restantes_por_variancia = restantes.sort_values(
        ["engajamento_var", "engajamento_medio"], ascending=False
    )
    label_viral = restantes_por_variancia.iloc[0]["cluster_label"]
    labels_curto = restantes.loc[
        restantes["cluster_label"] != label_viral, "cluster_label"
    ].tolist()

    cartoes: dict[str, dict] = {
        GRUPO_LONGO: _combinar_grupo(puros[puros["cluster_label"] == label_longo]),
        GRUPO_VIRAL: _combinar_grupo(
            pd.concat([puros[puros["cluster_label"] == label_viral], ruido], ignore_index=True)
        ),
    }
    if labels_curto:
        cartoes[GRUPO_CURTO] = _combinar_grupo(
            puros[puros["cluster_label"].isin(labels_curto)]
        )
    return cartoes


def _grupo_maior_engajamento(cartoes: dict[str, dict]) -> str | None:
    """Nome do cartão (`GRUPO_*`) com maior `engajamento_medio` REAL --
    nunca hardcoda "curto, converte" como vencedor (issue #112, Implementation
    Decisions). `None` se `cartoes` estiver vazio. Empate quebrado por
    `_ORDEM_CARTOES` (determinístico)."""
    if not cartoes:
        return None
    ordem = {nome: i for i, nome in enumerate(_ORDEM_CARTOES)}
    return min(
        cartoes,
        key=lambda nome: (-cartoes[nome]["engajamento_medio"], ordem.get(nome, len(ordem))),
    )


# ---------------------------------------------------------------------------
# Recomendação principal (tema prioritário x formato vencedor)
# ---------------------------------------------------------------------------


def _topico_prioritario_ajustado(
    fila_prioridade: pd.DataFrame, df_discurso_governador: pd.DataFrame
) -> pd.Series | None:
    """Topo da `fila_prioridade`, mas pulando temas que a assessoria já
    produz muito discurso oficial sobre (`governor_discourse_topics`, já
    filtrado ao governador) -- issue #112, user story 6: "não recomendar um
    tema que a assessoria já está cobrindo bastante". Um tema é "muito
    coberto" quando o volume de menções no discurso oficial está acima da
    mediana entre os tópicos com discurso deste governador.

    Se `df_discurso_governador` estiver vazia/sem `Topic` (dado ainda não
    disponível), ou se TODOS os temas da fila estiverem muito cobertos,
    degrada para o topo puro da fila -- nunca retorna `None` só por causa do
    cruzamento com discurso. `None` só quando `fila_prioridade` já está
    vazia."""
    if fila_prioridade.empty:
        return None
    if df_discurso_governador.empty or "Topic" not in df_discurso_governador.columns:
        return fila_prioridade.iloc[0]

    volume = df_discurso_governador.dropna(subset=["Topic"]).groupby("Topic").size()
    if volume.empty:
        return fila_prioridade.iloc[0]

    limiar = volume.median()
    for _, linha in fila_prioridade.iterrows():
        if volume.get(linha["Topic"], 0) <= limiar:
            return linha
    # Todos os temas da fila estão muito cobertos -- ainda assim recomenda o
    # topo (nunca deixa a recomendação vazia por esse motivo sozinho).
    return fila_prioridade.iloc[0]


def _recomendacao_principal(
    fila_prioridade: pd.DataFrame,
    df_discurso_governador: pd.DataFrame,
    cartoes: dict[str, dict],
) -> dict | None:
    """Recomendação principal: tema do topo da fila (ajustado contra
    discurso já produzido, ver `_topico_prioritario_ajustado`) + formato com
    maior engajamento médio REAL entre os cartões calculados (ver
    `_grupo_maior_engajamento`) -- nunca hardcoda "curto" como formato
    vencedor. `None` se não houver tema OU não houver cartão de formato
    calculável (nunca força uma recomendação sem as duas metades)."""
    topico = _topico_prioritario_ajustado(fila_prioridade, df_discurso_governador)
    if topico is None:
        return None
    grupo = _grupo_maior_engajamento(cartoes)
    if grupo is None:
        return None
    return {"topic_name": topico["Name"], "grupo": grupo}


# ---------------------------------------------------------------------------
# render()
# ---------------------------------------------------------------------------


def render() -> None:
    df_metadata = data.load_governors_metadata()
    df_engagement = data.load_engagement()

    options = _governor_options(df_metadata)
    if not options and not df_engagement.empty and "inputUrl" in df_engagement.columns:
        urls = df_engagement["inputUrl"].dropna().unique().tolist()
        options = {url: url for url in urls}

    if not options:
        st.selectbox("Governador", options=[_PLACEHOLDER_SEM_GOVERNADOR], disabled=True)
        stage_label("Reach + Act (Consumir)")
        st.info(
            "Nenhum governador disponível ainda -- rode a pipeline "
            "(`uv run python pipeline.py`) para popular o dashboard."
        )
        footnote()
        return

    nome_selecionado = st.selectbox("Governador", options=list(options.keys()))
    governor_url = options[nome_selecionado]
    stage_label("Reach + Act (Consumir)")

    # ---- Dado bruto ----
    df_topic_priority = data.load_topic_priority()
    df_sentiment_governador = data.comments_only(
        _filtrar_por_governador(data.load_sentiment(), governor_url)
    )
    topicos_governador = _topicos_do_governador(df_sentiment_governador)
    fila = _fila_prioridade(df_topic_priority, topicos_governador)

    df_discurso_governador = _filtrar_por_governador(data.load_discourse_topics(), governor_url)

    df_clusters_reel_governador = _clusters_reel_do_governador(
        data.load_clusters_content(), data.load_reels_content(), governor_url
    )
    estatisticas = _estatisticas_por_grupo(df_clusters_reel_governador)
    cartoes = _mapear_grupos_para_cartoes(estatisticas)

    # ---- Frase de decisão (recomendação principal) ----
    recomendacao = _recomendacao_principal(fila, df_discurso_governador, cartoes)
    if recomendacao is None:
        decision_band(
            "Ainda não há tópicos priorizados e/ou Reels classificados o "
            "suficiente para recomendar o próximo post deste governador.",
            level="info",
        )
    else:
        decision_band(
            f'Priorize Reels no formato "{recomendacao["grupo"]}" sobre '
            f'"{recomendacao["topic_name"]}" -- maior prioridade nos '
            "comentários e o formato que mais engaja entre os Reels deste "
            "governador.",
            level="good",
        )

    # ---- Fila de temas priorizados ----
    st.markdown(
        "#### Fila de temas por prioridade",
        help=(
            'Prioridade estima impacto x confiança (Score ICE). "% positivo" '
            "é a proporção de comentários positivos sobre este tema. O "
            "alcance usado no cálculo é sempre uma ESTIMATIVA por "
            "engajamento (curtidas + respostas dos comentários), não "
            "visualizações reais -- não superinterpretar o número."
        ),
    )
    if fila.empty:
        st.info(
            "Nenhum tema priorizado disponível para este governador ainda "
            "-- rode `scripts/run_modeling.py` para gerar `topic_priority_score` "
            "e garantir que este governador tenha comentários com tópico "
            "atribuído."
        )
    else:
        df_exibir = fila[["Name", "proporcao_sentimento_positivo", "Prioridade"]].copy()
        df_exibir["proporcao_sentimento_positivo"] = df_exibir[
            "proporcao_sentimento_positivo"
        ].map(_fmt_pct)
        df_exibir = df_exibir.rename(
            columns={"Name": "Tema", "proporcao_sentimento_positivo": "% positivo"}
        )
        st.dataframe(df_exibir, hide_index=True, width="stretch")

    # ---- Cartões de formato ----
    st.markdown("#### Formatos de Reel")
    colunas = st.columns(3)
    for col, nome_grupo in zip(colunas, _ORDEM_CARTOES, strict=True):
        with col:
            st.markdown(f"**{nome_grupo.capitalize()}**")
            stats = cartoes.get(nome_grupo)
            if stats is None:
                st.caption("Sem Reel classificado neste grupo para este governador ainda.")
            else:
                st.write(f"{stats['n']} reel(s)")
                st.caption(f"Engajamento médio: {_fmt_int_br(stats['engajamento_medio'])}")

    footnote()
