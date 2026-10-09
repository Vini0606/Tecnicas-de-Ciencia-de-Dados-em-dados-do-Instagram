"""Tela 2 -- "O que produzir" (ADR 0021 / issue #112).

Responde "o que eu posto a seguir?" combinando duas fontes que hoje vivem
espalhadas em páginas técnicas (`pages/02_insights.py`, seção Score ICE, e
`pages/03_performance.py`, clusters de conteúdo): uma fila de pautas
priorizadas (`content_topic_priority_score`) e três cartões de formato de Reel
(`governor_clusters`), mais uma recomendação principal cruzando as duas.

Mesma estrutura fixa da Tela 1 (ver `dashboard/screens/resumo.py`, ADR 0021 --
Princípio de design): cabeçalho (governador) -> `stage_label` -> frase de
decisão -> prova (fila + cartões) -> rodapé. Toda a lógica de decisão vive em
funções puras nomeadas abaixo, testadas em
`tests/test_dashboard_screens_produzir.py` -- `render()` só orquestra I/O do
Streamlit sobre o resultado dessas funções, nunca calcula nada sozinho (mesmo
padrão da Tela 1).

Histórico: a ADR 0024 acrescentou aqui uma seção "Evidência histórica de
desempenho" e a ADR 0026 / issue #154 a migrou para o Resumo, deixando um link
"Ver evidência completa no Resumo". A ADR 0031 removeu a evidência do Resumo
(substituída por linhas mensais em "Comparar perfis"), então o link também
saiu desta tela.

ADR 0026 / issue #154 também trouxe para cá 2 dos 4 antigos "Destaques da
execução" do Resumo -- "Melhor post" e "Alto potencial, pouco publicado" --
portados do Resumo (migrados para pautas na issue #191), posicionados logo depois
de "Formatos de Reel": ambas são
perguntas de "o que produzir", não de "como estamos indo" (ver ADR 0021).

ADR 0028 / issue #166 acrescentou um filtro de prioridade (botão único --
`_OPCOES_FILTRO_PRIORIDADE`/`_filtrar_fila_por_prioridade`) e a coluna
"Comentários" (`n_comentarios`) na fila -- ambos puramente aditivos sobre o
resultado já calculado por `_fila_prioridade`, sem mudar `score`,
`_selo_prioridade`/`_cortes_tercis` nem `_recomendacao_principal`/
`_pauta_prioritaria_ajustada`, que continuam operando sobre a fila
completa, nunca a filtrada. `n_comentarios` é GLOBAL (mesmo escopo de
`score`/`% positivo`), nunca recalculado só sobre os
comentários do governador selecionado.

ADR 0028 / issue #167 acrescentou um popup (`st.dialog`) com os comentários
GLOBAIS de uma linha da fila, aberto ao clicar nela
(`st.dataframe(..., on_select="rerun", selection_mode="single-row")`).
`_comentarios_da_pauta` faz o filtro/ordenação/corte (top-50 por
engajamento); `render()` só resolve a linha clicada de volta pra pauta
correspondente em `fila_filtrada` (mesmo índice posicional do `st.dataframe`
exibido) e chama o dialog.

Issue #191 (spec #182) substituiu a fila de grupos de comentários por
uma FILA DE PAUTAS (assunto do conteúdo): a fonte passa a ser
`content_topic_priority_score` (ICE por pauta, issue #190), ranking global
sobre todos os perfis. "Filtrado ao governador" significa: só as pautas em
que ele tem pelo menos um reel com pauta de legenda (`governor_discourse_
topics`); `score`/`n_comentarios`/selo seguem globais. O popup lista os
comentários dos reels da pauta, ligados por `id_reel`. Decisões de migração
das lógicas dependentes da fila (recomendação principal, pauta prioritária
ajustada, destaque "Alto potencial, pouco publicado") estão nas docstrings das
respectivas funções: todas passaram a operar sobre pautas, e pautas
degeneradas ("sem assunto definido") nunca são recomendadas. Grupos de
comentários (modelo de grupos de comentários) saíram da fila e ganharam seção
própria, "Maiores grupos de comentários" (issue #192).
"""

from __future__ import annotations

import html
import re

import pandas as pd
import streamlit as st

from dashboard.core import data
from dashboard.core.components import decision_band, footnote, stage_label
from dashboard.core.rotulos import rotulo_se_emoji
from src.modeling.topic_labels import DEGENERATE_TOPIC_LABEL

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
FILTRO_TODAS = "Todas"
"""Valor do filtro de prioridade (ADR 0028 / issue #166) que significa "sem
filtro" -- nunca um selo de prioridade real, só a opção default do controle
de botões acima da fila."""
_OPCOES_FILTRO_PRIORIDADE = [FILTRO_TODAS, SELO_ALTA, SELO_MEDIA, SELO_CUIDADO]


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
    return dict(
        sorted(zip(nomes, pares["inputUrl"], strict=True), key=lambda kv: kv[0])
    )


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
    return f"{round(valor):,}".replace(",", ".")


# ---------------------------------------------------------------------------
# Fila de pautas (Score ICE por pauta -> selo, nunca o score bruto)
# ---------------------------------------------------------------------------

_COLUNAS_FILA = [
    "Topic",
    "Name",
    "Pauta",
    "score",
    "n_comentarios",
    "proporcao_sentimento_positivo",
    "Prioridade",
]

_MAX_CHARS_ROTULO = 60
_PREFIXO_ID_RE = re.compile(r"^-?\d+_")


def _rotulo_exibicao(name: object) -> str:
    """Rótulo de pauta pronto para a fila. Aceita o `Name` gravado em
    `content_topic_priority_score` nos 3 formatos que existem na prática:
    lista de palavras-chave bruta ("mobiliza, 0001, elmano"), rótulo refinado
    pelo Gemini ("Entregas de obras, obra, entrega" -- só o rótulo, antes da
    primeira vírgula, é exibido) e degenerado/nulo ("sem assunto definido").
    Tolera o prefixo `<id>_` do BERTopic caso ainda venha no nome. Listas
    longas são truncadas com reticências -- nunca lança exceção."""
    if name is None or pd.isna(name):
        return DEGENERATE_TOPIC_LABEL
    texto = _PREFIXO_ID_RE.sub("", str(name).strip(), count=1).replace("_", ", ")
    partes = [p.strip() for p in texto.split(",") if p.strip()]
    if not partes:
        return DEGENERATE_TOPIC_LABEL
    if " " in partes[0]:
        # Rótulo refinado ("rótulo, kw1, kw2"): só o rótulo.
        texto = partes[0]
    else:
        texto = ", ".join(partes)
    if len(texto) > _MAX_CHARS_ROTULO:
        texto = texto[: _MAX_CHARS_ROTULO - 1].rstrip(", ") + "…"
    return texto


def _eh_degenerada(name: object) -> bool:
    """`True` para pauta sem assunto definido -- continua visível na fila,
    mas nunca vira recomendação."""
    return _rotulo_exibicao(name) == DEGENERATE_TOPIC_LABEL


def _cortes_tercis(df_pautas: pd.DataFrame) -> tuple[float, float]:
    """`(corte_alta, corte_media)` -- os 2 cortes de tercil do `score` ICE
    sobre TODO `content_topic_priority_score` (ranking global de pautas, não
    só as pautas do governador selecionado). `(0.0, 0.0)` se a tabela estiver
    vazia ou sem `score` -- nunca lança exceção."""
    if df_pautas.empty or "score" not in df_pautas.columns:
        return (0.0, 0.0)
    scores = df_pautas["score"].dropna()
    if scores.empty:
        return (0.0, 0.0)
    return (float(scores.quantile(2 / 3)), float(scores.quantile(1 / 3)))


def _selo_prioridade(score: float | None, corte_alta: float, corte_media: float) -> str:
    """Selo de prioridade determinístico a partir do `score` ICE bruto e dos
    2 cortes de tercil (ver `_cortes_tercis`) -- nunca exibe o score em si.
    Cortes inclusivos do lado alto: `score == corte` entra na banda melhor."""
    if score is None or pd.isna(score):
        return SELO_CUIDADO
    if score >= corte_alta:
        return SELO_ALTA
    if score >= corte_media:
        return SELO_MEDIA
    return SELO_CUIDADO


def _reels_por_pauta(df_discurso: pd.DataFrame) -> pd.DataFrame:
    """`id_reel` -> `Topic` (a pauta), uma linha por reel: só a legenda define
    pauta (`fonte == "legenda"`, quando a coluna existe), ruído (`Topic ==
    -1`) fica fora e `governor_discourse_topics` tem reels repetidos, então
    mantém a primeira ocorrência -- mesma regra de
    `ContentTopicPriorityScorer.score`, para que a fila e o popup enxerguem
    exatamente os reels que entraram no ICE. `DataFrame` vazio (colunas
    `id_reel`/`Topic`) se faltar dado."""
    vazio = pd.DataFrame(columns=["id_reel", "Topic"])
    if df_discurso.empty or not {"id_reel", "Topic"}.issubset(df_discurso.columns):
        return vazio
    df = df_discurso
    if "fonte" in df.columns:
        df = df[df["fonte"] == "legenda"]
    df = df.dropna(subset=["id_reel", "Topic"])
    df = df[df["Topic"] != -1].drop_duplicates(subset="id_reel", keep="first")
    return df[["id_reel", "Topic"]].reset_index(drop=True)


def _pautas_do_governador(df_discurso_governador: pd.DataFrame) -> set:
    """`Topic`s (pautas) em que o governador tem pelo menos um reel com pauta
    de legenda (`df_discurso_governador` já filtrado por
    `_filtrar_por_governador`). Conjunto vazio -- nunca exceção -- se não
    houver legenda modelada."""
    return set(_reels_por_pauta(df_discurso_governador)["Topic"].tolist())


def _fila_prioridade(df_pautas: pd.DataFrame, pautas_governador: set) -> pd.DataFrame:
    """Fila de pautas deste governador: `content_topic_priority_score`
    restrito a `pautas_governador`, ordenado por `score` ICE decrescente, com
    o selo de prioridade. `score`, `n_comentarios` e `% positivo` ficam GLOBAIS
    e o selo vem dos tercis do ranking global (nunca recalculados só sobre o
    governador, para o selo não oscilar por perfil). `DataFrame` vazio
    (colunas `_COLUNAS_FILA`, nunca exceção) se a tabela estiver vazia ou se
    o governador não tiver pauta.

    `Topic`/`Name`/`score` seguem como colunas internas (para a recomendação
    e o popup); `render()` exibe só Pauta/Comentários/% positivo/Prioridade."""
    required = {"Topic", "Name", "score", "proporcao_sentimento_positivo"}
    if df_pautas.empty or not required.issubset(df_pautas.columns):
        return pd.DataFrame(columns=_COLUNAS_FILA)
    if not pautas_governador:
        return pd.DataFrame(columns=_COLUNAS_FILA)

    df_pautas = df_pautas.copy()
    if "n_comentarios" not in df_pautas.columns:
        df_pautas["n_comentarios"] = pd.NA

    df = df_pautas[df_pautas["Topic"].isin(pautas_governador)]
    if df.empty:
        return pd.DataFrame(columns=_COLUNAS_FILA)

    corte_alta, corte_media = _cortes_tercis(df_pautas)
    df = df.sort_values(["score", "Topic"], ascending=[False, True]).reset_index(
        drop=True
    )
    df = df.assign(
        Pauta=df["Name"].map(_rotulo_exibicao),
        Prioridade=df["score"].apply(
            lambda s: _selo_prioridade(s, corte_alta, corte_media)
        ),
    )
    return df[_COLUNAS_FILA]


ESTADO_FILA_OK = "ok"
ESTADO_FILA_TABELA_AUSENTE = "tabela_ausente"
ESTADO_FILA_SEM_PAUTAS = "sem_pautas"


def _estado_fila(df_pautas: pd.DataFrame, fila: pd.DataFrame) -> str:
    """Qual mensagem `render()` mostra no lugar da fila: tabela de ICE ausente
    (orientar a rodar o estágio), governador sem pautas (sem legenda
    modelada) ou fila normal."""
    if df_pautas.empty:
        return ESTADO_FILA_TABELA_AUSENTE
    if fila.empty:
        return ESTADO_FILA_SEM_PAUTAS
    return ESTADO_FILA_OK


def _filtrar_fila_por_prioridade(fila: pd.DataFrame, selo: str | None) -> pd.DataFrame:
    """Filtro de botão único sobre a fila já calculada (ADR 0028 / issue
    #166) -- só uma lente de visualização: nunca recalcula o selo nem afeta a
    recomendação principal, que opera sobre a fila completa. `selo` igual a
    `FILTRO_TODAS` ou `None` retorna `fila` inteira. `fila` vazia retorna
    vazia, nunca exceção."""
    if fila.empty or selo is None or selo == FILTRO_TODAS:
        return fila
    return fila[fila["Prioridade"] == selo]


_COLUNAS_COMENTARIOS_POPUP = [
    "text",
    "sentiment_label",
    "likesCount",
    "repliesCount",
    "ownerUsername",
    "timestamp",
]


def _preparar_comentarios_popup(df: pd.DataFrame, top_n: int) -> pd.DataFrame:
    """Colunas do popup + ordenação por engajamento + corte (compartilhado
    entre o popup da fila de pautas e o dos grupos de comentários)."""
    df = df.copy()
    valores_default = {col: pd.NA for col in _COLUNAS_COMENTARIOS_POPUP}
    valores_default["likesCount"] = 0
    valores_default["repliesCount"] = 0
    for col, valor in valores_default.items():
        if col not in df.columns:
            df[col] = valor

    engajamento = pd.to_numeric(df["likesCount"], errors="coerce").fillna(
        0.0
    ) + pd.to_numeric(df["repliesCount"], errors="coerce").fillna(0.0)
    df = df.assign(_engajamento=engajamento).sort_values(
        "_engajamento", ascending=False
    )
    return df[_COLUNAS_COMENTARIOS_POPUP].head(top_n).reset_index(drop=True)


def _comentarios_da_pauta(
    df_comentarios: pd.DataFrame, df_discurso: pd.DataFrame, topic: int, top_n: int = 50
) -> pd.DataFrame:
    """Comentários GLOBAIS (todos os perfis) dos reels da pauta `topic`,
    ligados por `id_reel` (ver `_reels_por_pauta`) -- popup aberto ao clicar
    numa linha da fila. `df_comentarios` já deve vir só com comentários de
    público (`data.comments_only()`); `df_discurso` é
    `governor_discourse_topics` inteiro. O `Topic` do próprio comentário (grupo
    de comentários) é ignorado: pauta e grupo de comentários são conceitos
    distintos.

    Ordenado por engajamento (`likesCount + repliesCount`) decrescente,
    cortado nas `top_n` primeiras linhas; nulos contam como 0. `DataFrame`
    vazio com as colunas de `_COLUNAS_COMENTARIOS_POPUP` (nunca exceção) se
    faltar dado ou se a pauta não tiver comentário (pauta degenerada)."""
    vazio = pd.DataFrame(columns=_COLUNAS_COMENTARIOS_POPUP)
    if df_comentarios.empty or "id_reel" not in df_comentarios.columns:
        return vazio

    reels_pauta = _reels_por_pauta(df_discurso)
    ids = set(reels_pauta.loc[reels_pauta["Topic"] == topic, "id_reel"])
    df = df_comentarios[df_comentarios["id_reel"].isin(ids)]
    if df.empty:
        return vazio

    return _preparar_comentarios_popup(df, top_n)


# ---------------------------------------------------------------------------
# Maiores grupos de comentários (issue #192, spec #182)
# ---------------------------------------------------------------------------

SENTIMENTO_POSITIVO = "positive"
SENTIMENTO_NEGATIVO = "negative"
TOP_N_GRUPOS = 5
ROTULO_GRUPO_SEM_ROTULO = "Grupo sem rótulo definido"
_COLUNAS_GRUPOS = ["Topic", "Grupo", "n", "pct"]


def _rotulo_grupo(name: object) -> str:
    """Rótulo do grupo de comentários: reaproveita `_rotulo_exibicao` (bruto
    ou refinado); rótulo degenerado/nulo vira texto neutro, sem a palavra
    "assunto" (reservada a pauta). Grupos que são só emojis ("mãos aplaudindo",
    "tecla 3") ganham um nome legível (ADR 0038)."""
    emoji = rotulo_se_emoji(name)
    if emoji:
        return emoji
    rotulo = _rotulo_exibicao(name)
    return ROTULO_GRUPO_SEM_ROTULO if rotulo == DEGENERATE_TOPIC_LABEL else rotulo


def _maiores_grupos_de_comentarios(
    df_comentarios: pd.DataFrame,
    governor_url: str,
    sentimento: str,
    top_n: int = TOP_N_GRUPOS,
) -> pd.DataFrame:
    """Maiores grupos de comentários (`Topic` do modelo de comentários) do
    governador, por quantidade de comentários do `sentimento`. `df_comentarios`
    é `data.comments_only(data.load_sentiment())` (todos os perfis).

    Colunas: `Topic`, `Grupo` (rótulo de exibição), `n` (comentários do
    sentimento no grupo), `pct` (fração `n / total de comentários do
    governador`, incluindo neutros e ruído, em 0-1). Ruído (`Topic == -1`) e
    `Topic` nulo ficam de fora; empate de `n` desempata por `Topic` crescente.
    Menos de `top_n` grupos -> menos linhas; `DataFrame` vazio se não houver
    nenhum (ou faltar dado) -- nunca exceção."""
    vazio = pd.DataFrame(columns=_COLUNAS_GRUPOS)
    colunas = {"Topic", "sentiment_label"}
    df = _filtrar_por_governador(df_comentarios, governor_url)
    if df.empty or not colunas.issubset(df.columns):
        return vazio
    total = len(df)
    df = df[
        (df["sentiment_label"] == sentimento)
        & df["Topic"].notna()
        & (df["Topic"] != -1)
    ]
    if df.empty:
        return vazio

    nomes = df["Name"] if "Name" in df.columns else pd.Series(pd.NA, index=df.index)
    df = df.assign(_name=nomes)
    grupos = (
        df.groupby("Topic")
        .agg(n=("Topic", "size"), _name=("_name", "first"))
        .reset_index()
        .sort_values(["n", "Topic"], ascending=[False, True])
        .head(top_n)
        .reset_index(drop=True)
    )
    grupos["Grupo"] = grupos["_name"].map(_rotulo_grupo)
    grupos["pct"] = grupos["n"] / total
    return grupos[_COLUNAS_GRUPOS]


def _comentarios_do_grupo(
    df_comentarios: pd.DataFrame,
    governor_url: str,
    topic: int,
    sentimento: str,
    top_n: int = 50,
) -> pd.DataFrame:
    """Comentários do popup de um grupo de comentários: só do governador e do
    `sentimento` do painel, mesma ordenação/colunas/limite de
    `_comentarios_da_pauta`. `DataFrame` vazio com colunas se faltar dado."""
    vazio = pd.DataFrame(columns=_COLUNAS_COMENTARIOS_POPUP)
    df = _filtrar_por_governador(df_comentarios, governor_url)
    if df.empty or not {"Topic", "sentiment_label"}.issubset(df.columns):
        return vazio
    df = df[(df["Topic"] == topic) & (df["sentiment_label"] == sentimento)]
    if df.empty:
        return vazio
    return _preparar_comentarios_popup(df, top_n)


# ---------------------------------------------------------------------------
# Cartões de formato (cluster_label -> grupo de negócio)
# ---------------------------------------------------------------------------


def _clusters_reel_do_governador(
    df_clusters: pd.DataFrame, df_reels: pd.DataFrame, governor_url: str
) -> pd.DataFrame:
    """Reels do governador (`content_type == 'reel'`) com `cluster_label`,
    `Total de Engajamento` e `videoDuration` juntos numa linha -- mesmo join
    `id`/`id_reel` de `governor_clusters` com `reels_clean` já usado em
    `_melhor_post` abaixo (ver docstring de `data.load_reels_content`:
    `governor_clusters` sozinha não tem `inputUrl` nem métrica de
    engajamento por post). `DataFrame` vazio (nunca exceção) se qualquer
    tabela estiver vazia, sem match, ou sem as colunas esperadas."""
    if df_clusters.empty or df_reels.empty or not governor_url:
        return pd.DataFrame()
    if (
        "content_type" not in df_clusters.columns
        or "id_reel" not in df_clusters.columns
    ):
        return pd.DataFrame()

    clusters_reel = df_clusters[df_clusters["content_type"] == "reel"]
    if clusters_reel.empty:
        return pd.DataFrame()

    reels_governador = _filtrar_por_governador(df_reels, governor_url)
    if reels_governador.empty or "id" not in reels_governador.columns:
        return pd.DataFrame()

    return reels_governador.merge(
        clusters_reel, left_on="id", right_on="id_reel", how="inner"
    )


def _estatisticas_por_grupo(df_clusters_reel_governador: pd.DataFrame) -> pd.DataFrame:
    """1 linha por `cluster_label` (incluindo -1 = ruído): `n`,
    `engajamento_medio`, `engajamento_var` (variância amostral, 0.0 quando
    `n < 2` -- sem sinal de variância com 1 só reel) e `duracao_media`
    (`NaN` se `videoDuration` não existir/estiver sempre nula). `DataFrame`
    vazio se a entrada estiver vazia ou sem `cluster_label`/`Total de
    Engajamento`."""
    required = {"cluster_label", "Total de Engajamento"}
    colunas = [
        "cluster_label",
        "n",
        "engajamento_medio",
        "engajamento_var",
        "duracao_media",
    ]
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
    engajamento_medio = float(
        (linhas["engajamento_medio"] * linhas["n"]).sum() / n_total
    )
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
        return {
            GRUPO_VIRAL: _combinar_grupo(pd.concat([puros, ruido], ignore_index=True))
        }

    puros_por_duracao = puros.sort_values(
        "duracao_media", ascending=False, na_position="last"
    )
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
            pd.concat(
                [puros[puros["cluster_label"] == label_viral], ruido], ignore_index=True
            )
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
        key=lambda nome: (
            -cartoes[nome]["engajamento_medio"],
            ordem.get(nome, len(ordem)),
        ),
    )


# ---------------------------------------------------------------------------
# Recomendação principal (pauta prioritária x formato vencedor)
# ---------------------------------------------------------------------------


def _pauta_prioritaria_ajustada(
    fila_prioridade: pd.DataFrame, df_discurso_governador: pd.DataFrame
) -> pd.Series | None:
    """Topo da `fila_prioridade`, mas pulando pautas sobre as quais o
    governador já publica muito (número de reels dele na pauta acima da
    mediana entre as pautas em que ele publica) -- issue #112, user story 6:
    "não recomendar um assunto que a assessoria já está cobrindo bastante".
    Pautas degeneradas ("sem assunto definido") nunca são recomendadas.

    Migrada de grupos de comentários para pautas (issue #191): a antiga
    comparação com o discurso cruzava `Topic` de dois modelos diferentes;
    agora a pauta e o volume de discurso vêm do mesmo modelo de legendas.

    Sem dado de discurso, ou se TODAS as pautas candidatas estiverem muito
    cobertas, degrada para o topo das candidatas. `None` só quando não há
    candidata (fila vazia ou só pautas degeneradas)."""
    if fila_prioridade.empty:
        return None
    candidatas = fila_prioridade[~fila_prioridade["Name"].map(_eh_degenerada)]
    if candidatas.empty:
        return None

    volume = _reels_por_pauta(df_discurso_governador).groupby("Topic").size()
    if volume.empty:
        return candidatas.iloc[0]

    limiar = volume.median()
    for _, linha in candidatas.iterrows():
        if volume.get(linha["Topic"], 0) <= limiar:
            return linha
    return candidatas.iloc[0]


def _recomendacao_principal(
    fila_prioridade: pd.DataFrame,
    df_discurso_governador: pd.DataFrame,
    cartoes: dict[str, dict],
) -> dict | None:
    """Recomendação principal: pauta do topo da fila (ajustada contra o
    discurso já produzido, ver `_pauta_prioritaria_ajustada`) + formato com
    maior engajamento médio REAL entre os cartões (ver
    `_grupo_maior_engajamento`). `None` se não houver pauta OU cartão de
    formato calculável (nunca força uma recomendação sem as duas metades)."""
    pauta = _pauta_prioritaria_ajustada(fila_prioridade, df_discurso_governador)
    if pauta is None:
        return None
    grupo = _grupo_maior_engajamento(cartoes)
    if grupo is None:
        return None
    return {"pauta": pauta["Pauta"], "grupo": grupo}


# ---------------------------------------------------------------------------
# Destaques (ADR 0026 / issue #154) -- "Melhor post" e "Alto potencial,
# pouco publicado" (este migrado para pautas na issue #191); ambos
# respondem "o que produzir?".
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
    join já usado em `_clusters_reel_do_governador` acima. `None` se
    qualquer uma das tabelas estiver vazia ou sem match -- nunca lança
    exceção."""
    if df_clusters.empty or df_reels.empty or not governor_url:
        return None
    if (
        "content_type" not in df_clusters.columns
        or "id_reel" not in df_clusters.columns
    ):
        return None

    clusters_reel = df_clusters[df_clusters["content_type"] == "reel"]
    if clusters_reel.empty:
        return None

    reels_governador = _filtrar_por_governador(df_reels, governor_url)
    if reels_governador.empty or "Total de Engajamento" not in reels_governador.columns:
        return None
    if "id" not in reels_governador.columns:
        return None

    merged = reels_governador.merge(
        clusters_reel, left_on="id", right_on="id_reel", how="inner"
    )
    if merged.empty:
        return None

    linha = merged.sort_values("Total de Engajamento", ascending=False).iloc[0]
    return {
        "id": linha.get("id"),
        "shortCode": linha.get("shortCode"),
        "total_engajamento": linha["Total de Engajamento"],
    }


SEM_DADO_DISCURSO = "sem_dado_discurso"
"""Sentinela retornada por `_pauta_alto_positivo_pouco_publicada` quando o
governador não tem legenda modelada -- distinta de `None` (sem pauta
calculável) para que `render()` mostre a mensagem amigável específica."""


def _pauta_alto_positivo_pouco_publicada(
    df_pautas: pd.DataFrame, df_discurso_governador: pd.DataFrame
) -> dict | str | None:
    """Pauta com `proporcao_sentimento_positivo` na mediana ou acima (entre
    as pautas com assunto definido) e menos reels PUBLICADOS por este
    governador -- "o público recebe bem, e este perfil pouco publica sobre
    isso". Pautas em que o governador não tem reel contam volume 0 (são as
    maiores oportunidades). Desempate pelo maior `score`.

    Migrada de grupos de comentários para pautas (issue #191). Retorna
    `SEM_DADO_DISCURSO` se `df_discurso_governador` não tiver legenda
    modelada; `None` se não houver pauta candidata."""
    required = {"Topic", "Name", "proporcao_sentimento_positivo"}
    if df_pautas.empty or not required.issubset(df_pautas.columns):
        return None
    reels = _reels_por_pauta(df_discurso_governador)
    if reels.empty:
        return SEM_DADO_DISCURSO

    df = df_pautas[~df_pautas["Name"].map(_eh_degenerada)]
    if df.empty:
        return None
    volume = reels.groupby("Topic").size().rename("volume_reels").reset_index()
    merged = df.merge(volume, on="Topic", how="left")
    merged["volume_reels"] = merged["volume_reels"].fillna(0)
    if "score" not in merged.columns:
        merged["score"] = 0.0

    limiar = merged["proporcao_sentimento_positivo"].median()
    candidatos = merged[merged["proporcao_sentimento_positivo"] >= limiar]
    if candidatos.empty:
        return None
    linha = candidatos.sort_values(
        ["volume_reels", "score"], ascending=[True, False]
    ).iloc[0]
    return {
        "topic": linha["Topic"],
        "pauta": _rotulo_exibicao(linha["Name"]),
        "proporcao_positivo": linha["proporcao_sentimento_positivo"],
        "volume_reels": linha["volume_reels"],
    }


# ---------------------------------------------------------------------------
# Popup de comentários (ADR 0028 / issue #167) -- 100% orquestração de
# widget (título dinâmico do `st.dialog` por pauta), nada de lógica pura pra
# extrair daqui; a lógica em si (filtro/ordenação/corte) já está em
# `_comentarios_da_pauta`, testada isoladamente.
# ---------------------------------------------------------------------------

_SESSION_KEY_PAUTA_POPUP = "produzir_pauta_popup_aberta"
"""Chave de `st.session_state` que guarda o `Topic` da última pauta cujo popup
foi aberto -- evita reabrir o mesmo popup a cada rerun enquanto a seleção do
`st.dataframe` da fila persistir (ver `render()`)."""


def _abrir_dialog_comentarios(
    nome_pauta: str, topic: int, df_comentarios: pd.DataFrame, df_discurso: pd.DataFrame
) -> None:
    @st.dialog(f'Comentários sobre a pauta "{nome_pauta}"')
    def _dialog() -> None:
        comentarios = _comentarios_da_pauta(df_comentarios, df_discurso, topic)
        if comentarios.empty:
            st.caption("Nenhum comentário encontrado para esta pauta.")
        else:
            st.dataframe(comentarios, hide_index=True, width="stretch")

    _dialog()


def _abrir_dialog_grupo(
    nome_grupo: str,
    topic: int,
    sentimento: str,
    governor_url: str,
    df_comentarios: pd.DataFrame,
) -> None:
    rotulo_sentimento = (
        "positivos" if sentimento == SENTIMENTO_POSITIVO else "negativos"
    )

    @st.dialog(f'Comentários {rotulo_sentimento} do grupo "{nome_grupo}"')
    def _dialog() -> None:
        comentarios = _comentarios_do_grupo(
            df_comentarios, governor_url, topic, sentimento
        )
        if comentarios.empty:
            st.caption("Nenhum comentário encontrado para este grupo.")
        else:
            st.dataframe(comentarios, hide_index=True, width="stretch")

    _dialog()


_CSS_GRUPOS = """
<style>
.gc-row { margin: 2px 0 6px; }
.gc-head { display: flex; justify-content: space-between; gap: 8px; font-size: 14px; }
.gc-count { white-space: nowrap; font-variant-numeric: tabular-nums; }
.gc-track { height: 8px; border-radius: 4px; background: rgba(128,128,128,.22); margin-top: 4px; }
.gc-bar { height: 8px; border-radius: 4px; }
.gc-pos { --gc: #0F6E56; }
.gc-neg { --gc: #A32D2D; }
.gc-bar { background: var(--gc); }
@media (prefers-color-scheme: dark) {
  .gc-pos { --gc: #5DCAA5; }
  .gc-neg { --gc: #F09595; }
}
</style>
"""


def _html_linha_grupo(grupo: str, n: int, pct: float, maximo: int, classe: str) -> str:
    largura = 0.0 if maximo <= 0 else 100.0 * n / maximo
    return (
        f'<div class="gc-row {classe}"><div class="gc-head"><span>{html.escape(grupo)}</span>'
        f'<span class="gc-count">{_fmt_int_br(n)} · {_fmt_pct(pct)}</span></div>'
        f'<div class="gc-track"><div class="gc-bar" style="width:{largura:.1f}%"></div></div></div>'
    )


def _render_painel_grupos(
    titulo: str,
    sentimento: str,
    classe: str,
    df_comentarios: pd.DataFrame,
    governor_url: str,
) -> None:
    st.markdown(f"**{titulo}**")
    grupos = _maiores_grupos_de_comentarios(df_comentarios, governor_url, sentimento)
    if grupos.empty:
        st.caption(
            f"Nenhum grupo de comentários {titulo.lower()} para este governador."
        )
        return
    maximo = int(grupos["n"].max())
    for linha in grupos.itertuples():
        st.markdown(
            _html_linha_grupo(
                linha.Grupo, int(linha.n), float(linha.pct), maximo, classe
            ),
            unsafe_allow_html=True,
        )
        if st.button(
            "Ver comentários",
            key=f"grupo_{sentimento}_{linha.Topic}",
            help=f"Abre os comentários {titulo.lower()} do grupo.",
        ):
            _abrir_dialog_grupo(
                linha.Grupo, linha.Topic, sentimento, governor_url, df_comentarios
            )


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
    df_pautas = data.load_content_topic_priority()
    df_discurso_global = data.load_discourse_topics()
    df_discurso_governador = _filtrar_por_governador(df_discurso_global, governor_url)
    fila = _fila_prioridade(df_pautas, _pautas_do_governador(df_discurso_governador))

    df_clusters_reel_governador = _clusters_reel_do_governador(
        data.load_clusters_content(), data.load_reels_content(), governor_url
    )
    estatisticas = _estatisticas_por_grupo(df_clusters_reel_governador)
    cartoes = _mapear_grupos_para_cartoes(estatisticas)

    # ---- Frase de decisão (recomendação principal) ----
    recomendacao = _recomendacao_principal(fila, df_discurso_governador, cartoes)
    if recomendacao is None:
        decision_band(
            "Ainda não há pautas priorizadas e/ou Reels classificados o "
            "suficiente para recomendar o próximo post deste governador.",
            level="info",
        )
    else:
        decision_band(
            f'Priorize Reels no formato "{recomendacao["grupo"]}" sobre a pauta '
            f'"{recomendacao["pauta"]}" -- os conteúdos dessa pauta estão '
            "associados a mais comentários positivos e esse é o formato que "
            "mais engaja entre os Reels deste governador.",
            level="good",
        )

    # ---- Fila de pautas priorizadas ----
    st.markdown(
        "#### Fila de pautas por prioridade",
        help=(
            "Pauta é o assunto dos conteúdos (legendas dos Reels). Prioridade "
            "estima impacto x confiança (Score ICE) sobre os comentários "
            'recebidos pelos Reels da pauta. "% positivo" é a proporção de '
            'comentários positivos nesses Reels. "Comentários" é a quantidade '
            "de comentários da pauta em TODOS os perfis (não só deste "
            "governador), mesmo escopo global do selo de prioridade e do % "
            "positivo. O alcance usado no cálculo é sempre uma ESTIMATIVA por "
            "engajamento (curtidas + respostas dos comentários), não "
            "visualizações reais -- uma associação, não uma causa."
        ),
    )
    # Filtro sempre visível, mesmo com a fila vazia (issue #166, user story 8).
    selo_selecionado = st.segmented_control(
        "Prioridade",
        options=_OPCOES_FILTRO_PRIORIDADE,
        selection_mode="single",
        default=FILTRO_TODAS,
    )
    estado_fila = _estado_fila(df_pautas, fila)
    if estado_fila == ESTADO_FILA_TABELA_AUSENTE:
        st.info(
            "O Score ICE por pauta ainda não foi gerado -- rode "
            "`scripts/run_modeling.py` para criar `content_topic_priority_score`."
        )
    elif estado_fila == ESTADO_FILA_SEM_PAUTAS:
        st.info(
            "Este governador ainda não tem pautas: nenhuma legenda de Reel "
            "modelada para ele. Rode a modelagem depois de coletar os Reels "
            "(`scripts/run_modeling.py`)."
        )
    else:
        fila_filtrada = _filtrar_fila_por_prioridade(fila, selo_selecionado)

        if fila_filtrada.empty:
            st.caption(f'Nenhuma pauta com prioridade "{selo_selecionado}" nesta fila.')
        else:
            df_exibir = fila_filtrada[
                [
                    "Pauta",
                    "n_comentarios",
                    "proporcao_sentimento_positivo",
                    "Prioridade",
                ]
            ].copy()
            df_exibir["n_comentarios"] = df_exibir["n_comentarios"].map(_fmt_int_br)
            df_exibir["proporcao_sentimento_positivo"] = df_exibir[
                "proporcao_sentimento_positivo"
            ].map(_fmt_pct)
            df_exibir = df_exibir.rename(
                columns={
                    "n_comentarios": "Comentários",
                    "proporcao_sentimento_positivo": "% positivo",
                }
            )
            evento = st.dataframe(
                df_exibir,
                hide_index=True,
                width="stretch",
                on_select="rerun",
                selection_mode="single-row",
            )
            # `on_select="rerun"` sempre devolve um `DataframeState`.
            linhas_selecionadas = evento.selection.rows
            if linhas_selecionadas:
                # `.iloc` posicional -- mesma ordem de exibição de `df_exibir`.
                linha_selecionada = fila_filtrada.iloc[linhas_selecionadas[0]]
                topic_selecionado = linha_selecionada["Topic"]
                # A seleção persiste no rerun disparado ao FECHAR o dialog --
                # sem guardar qual pauta já foi aberta, ele reabriria sozinho.
                if st.session_state.get(_SESSION_KEY_PAUTA_POPUP) != topic_selecionado:
                    st.session_state[_SESSION_KEY_PAUTA_POPUP] = topic_selecionado
                    df_comentarios_global = data.comments_only(data.load_sentiment())
                    _abrir_dialog_comentarios(
                        linha_selecionada["Pauta"],
                        topic_selecionado,
                        df_comentarios_global,
                        df_discurso_global,
                    )
            else:
                st.session_state.pop(_SESSION_KEY_PAUTA_POPUP, None)

    # ---- Maiores grupos de comentários (issue #192) ----
    st.markdown(
        "#### Maiores grupos de comentários",
        help=(
            "Grupos de comentários parecidos entre si, só dos comentários "
            "deste governador. A contagem é de comentários positivos (ou "
            "negativos) do grupo; a porcentagem é sobre o total de "
            "comentários do governador. Descreve o que o público diz, não o "
            "assunto do conteúdo. Comentários sem grupo definido ficam de fora."
        ),
    )
    st.caption("Comentários parecidos agrupados, do governador selecionado.")
    st.markdown(_CSS_GRUPOS, unsafe_allow_html=True)
    df_comentarios_publico = data.comments_only(data.load_sentiment())
    col_pos, col_neg = st.columns(2)
    with col_pos:
        _render_painel_grupos(
            "Positivos",
            SENTIMENTO_POSITIVO,
            "gc-pos",
            df_comentarios_publico,
            governor_url,
        )
    with col_neg:
        _render_painel_grupos(
            "Negativos",
            SENTIMENTO_NEGATIVO,
            "gc-neg",
            df_comentarios_publico,
            governor_url,
        )

    # ---- Cartões de formato ----
    st.markdown("#### Formatos de Reel")
    colunas = st.columns(3)
    for col, nome_grupo in zip(colunas, _ORDEM_CARTOES, strict=True):
        with col:
            st.markdown(f"**{nome_grupo.capitalize()}**")
            stats = cartoes.get(nome_grupo)
            if stats is None:
                st.caption(
                    "Sem Reel classificado neste grupo para este governador ainda."
                )
            else:
                st.write(f"{stats['n']} reel(s)")
                st.caption(
                    f"Engajamento médio: {_fmt_int_br(stats['engajamento_medio'])}"
                )

    # ---- Destaques (ADR 0026 / issue #154) ----
    # Posicionados logo depois de "Formatos de Reel" (ver docstring do
    # módulo).
    st.markdown("#### Destaques")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Melhor post**")
        # `data.load_reels_content()` retorna TODOS os 27 perfis --
        # `_melhor_post` filtra por `governor_url` internamente.
        df_reels_conteudo = data.load_reels_content()
        melhor = _melhor_post(
            data.load_clusters_content(), df_reels_conteudo, governor_url
        )
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
            st.write(
                f"`{identificador}` -- {_fmt_int_br(melhor['total_engajamento'])} de engajamento"
            )

    with col2:
        st.markdown("**Alto potencial, pouco publicado**")
        # Pautas globais x reels DESTE governador em cada uma (issue #191).
        pauta = _pauta_alto_positivo_pouco_publicada(df_pautas, df_discurso_governador)
        if pauta == SEM_DADO_DISCURSO:
            st.caption("Este governador ainda não tem legenda de Reel modelada.")
        elif pauta is None:
            st.caption("Sem pauta prioritária identificável nesta execução.")
        else:
            st.write(
                f"**{pauta['pauta']}** -- {_fmt_pct(pauta['proporcao_positivo'])} positivo, "
                f"{int(pauta['volume_reels'])} reel(s) deste governador."
            )

    footnote()
