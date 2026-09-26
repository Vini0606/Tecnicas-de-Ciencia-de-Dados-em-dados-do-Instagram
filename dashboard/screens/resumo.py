"""Tela 1 -- "Resumo da semana" (ADR 0021 / issue #111).

Home do novo dashboard: substitui o `app.py` antigo (raiz) e
`pages/01_explorar.py`. Estrutura fixa (ver ADR 0021, Princípio de design):
cabeçalho (só governador) -> frase de decisão semafórica -> KPIs (4
existentes + 2 de crescimento) -> prova (evidência histórica de desempenho)
-> rodapé.

ADR 0026 / issue #154 substituiu os antigos "Destaques da execução" (4
cartões narrativos) pela seção "Evidência histórica de desempenho" migrada
INTEIRA de "O que produzir" (vira a nova "prova" desta tela) + uma 2ª linha
de KPIs de crescimento (CMGR/retenção, sem delta). Das 2 informações
realmente exclusivas dos antigos destaques: "Melhor post" e "Alto potencial,
pouco discurso" migraram para "O que produzir" (critério idêntico, portado
sem redesenho); "Tema em alta de negatividade" virou uma 2ª leitura
exploratória no Radar de crise, reaproveitando o filtro de calendário que já
existe lá; "Publicações recentes" simplesmente desapareceu (já coberto pela
opção "Quantidade de publicações" do gráfico de evidência). O filtro de
calendário que antes vivia no cabeçalho (issue #150/ADR 0024) foi junto com
o destaque de negatividade -- o cabeçalho volta a ser só o seletor de
governador.

Toda a lógica de decisão (nível do semáforo, deltas, série de evidência)
vive em funções puras nomeadas abaixo, testadas em
`tests/test_dashboard_screens_resumo.py` -- `render()` só orquestra I/O do
Streamlit sobre o resultado dessas funções, nunca calcula nada sozinho (ver
issue #111, Testing Decisions).
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.core import data
from dashboard.core.components import decision_band, footnote, kpi_row, stage_label
from dashboard.core.deltas import (
    LIMIAR_NEGATIVIDADE_ALERTA,
    aggregate_metric_by_publication_day,
    compare_publication_window,
    compare_vs_historical_average,
    filter_by_date_range,
    normalize_date_input_range,
    quebrar_em_segmentos,
)
from dashboard.core.theme import COLORS

_PLACEHOLDER_SEM_GOVERNADOR = "—"

# ADR 0027 / issue #161: sentinela de "Todos os Governadores" no seletor --
# nunca uma URL real, tratado à parte em cada ponto de agregação abaixo.
# Não confundir com uma URL ausente (`governor_url is None`, "sem
# governador disponível ainda"): esta é uma seleção explícita e válida.
TODOS_OS_GOVERNADORES = "__todos_os_governadores__"
_LABEL_TODOS_OS_GOVERNADORES = "Todos os Governadores"


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


def _filtrar_por_governador_ou_todos(
    df: pd.DataFrame, governor_url: str, url_col: str = "inputUrl"
) -> pd.DataFrame:
    """`df` INTEIRO (sem filtro) quando `governor_url == TODOS_OS_GOVERNADORES`
    (ADR 0027 / issue #161) -- senão delega a `_filtrar_por_governador`.

    Uso restrito de propósito: só onde "todos os governadores juntos, sem
    distinguir" já é a semântica correta por construção -- hoje só o
    conteúdo do gráfico de evidência (`_conteudo_do_governador_por_tipo`),
    que soma/conta por dia sobre todas as linhas recebidas de qualquer
    forma. NUNCA usar nos pontos que fazem `.iloc[0]` esperando exatamente 1
    linha de snapshot por governador (KPIs de perfil/crescimento) -- esses
    têm seu próprio caminho de agregação explícito (soma ou média simples
    entre governadores) em `render()`, para não silenciosamente pegar só o
    1º governador da lista quando "Todos" está selecionado."""
    if governor_url == TODOS_OS_GOVERNADORES:
        return df
    return _filtrar_por_governador(df, governor_url, url_col)


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
# Agregação "Todos os Governadores" (ADR 0027 / issue #161) -- agregação
# SIMPLES, não ponderada por volume: soma para métricas de contagem
# (Seguidores), média aritmética simples entre governadores para métricas
# de proporção/taxa (% engajamento, % positivo, NSM, CMGR, retenção) -- cada
# governador pesa igual, nunca ponderado por quantos comentários/seguidores/
# publicações ele tem. Ver ADR 0027 para a justificativa completa e os
# riscos aceitos conscientemente (cobertura de governadores variando entre
# execuções para a soma de Seguidores).
# ---------------------------------------------------------------------------


def _proporcao_media_por_governador(df_comments_todos: pd.DataFrame, label: str) -> float | None:
    """Média aritmética SIMPLES (não ponderada por volume de comentários) da
    proporção de `sentiment_label == label` entre todos os governadores
    presentes em `df_comments_todos` -- cada governador calcula sua própria
    proporção primeiro (via `_chave`), só depois as proporções são
    calculadas; nunca agrega os comentários de todos os governadores num
    único pool antes de calcular a proporção (isso ponderaria pelo volume de
    cada perfil). `None` (nunca `ZeroDivisionError`) se `df_comments_todos`
    estiver vazio, sem a coluna `_chave`, ou sem nenhum governador com
    comentários."""
    se_faltando = df_comments_todos.empty or not {"sentiment_label", "_chave"}.issubset(
        df_comments_todos.columns
    )
    if se_faltando:
        return None
    proporcoes = df_comments_todos.groupby("_chave")["sentiment_label"].apply(
        lambda s: (s == label).sum() / len(s) if len(s) else None
    )
    proporcoes = proporcoes.dropna()
    if proporcoes.empty:
        return None
    return float(proporcoes.mean())


def _media_simples_por_indice(
    resultado_por_chave: dict[object, tuple], indice: int
) -> float | None:
    """Média aritmética simples do elemento `indice` de cada tupla-valor em
    `resultado_por_chave` (retorno de `compare_publication_window` com
    `key_col` != `None`, uma entrada por chave/governador) -- ignora chaves
    cujo valor nesse índice é `None` (ex.: governador sem dado na janela
    anterior). `None` (nunca `ZeroDivisionError`) se nenhuma chave tiver
    valor válido nesse índice."""
    valores = [v[indice] for v in resultado_por_chave.values() if v[indice] is not None]
    if not valores:
        return None
    return sum(valores) / len(valores)


def _delta_janela_publicacao_agregado(
    df_sentiment_history_todos: pd.DataFrame,
) -> tuple[object, float | None, float | None] | None:
    """Mesma ideia de `_delta_janela_publicacao_para_governador`, mas para
    "Todos os Governadores" (ADR 0027): cada governador é comparado nas
    SUAS PRÓPRIAS janelas atual/anterior primeiro
    (`compare_publication_window` com `key_col="_chave"`, uma janela por
    governador) -- só depois a MÉDIA SIMPLES é tirada sobre os valores por
    governador. Nunca agrega os comentários de todos os governadores num
    único pool antes de comparar (isso ponderaria pelo volume de comentários
    de cada perfil, não pelo número de perfis). `None` se não houver
    histórico suficiente -- mesma degradação graciosa da versão de 1
    governador."""
    if (
        df_sentiment_history_todos.empty
        or not {"sentiment_label", "_chave"}.issubset(df_sentiment_history_todos.columns)
    ):
        return None
    df = df_sentiment_history_todos.assign(
        _is_positive=(df_sentiment_history_todos["sentiment_label"] == "positive").astype(float)
    )
    resultado = compare_publication_window(df, value_col="_is_positive", key_col="_chave")
    if not resultado:
        return None

    valor_atual = _media_simples_por_indice(resultado, 0)
    if valor_atual is None:
        return None
    valor_anterior = _media_simples_por_indice(resultado, 2)
    delta_percentual = None
    if valor_anterior is not None and valor_anterior != 0:
        delta_percentual = (valor_atual - valor_anterior) / valor_anterior * 100
    return (valor_atual, delta_percentual, valor_anterior)


def _agregar_metrica_todos(df: pd.DataFrame, coluna: str, agg: str) -> float | None:
    """Soma (`agg="sum"`, métricas de contagem -- Seguidores) ou média
    aritmética SIMPLES (`agg="mean"`, métricas de proporção/taxa -- %
    engajamento, NSM, CMGR, retenção) de `coluna` em `df` -- um valor por
    linha (1 linha = 1 governador em `governor_engagement`/`governor_nsm`/
    `governor_growth_metrics`, sempre snapshot da execução mais recente,
    nunca histórico). `None` (nunca `0`/`NaN` fabricado) se `df` estiver
    vazio, sem a coluna, ou sem nenhum valor não-nulo."""
    if df.empty or coluna not in df.columns:
        return None
    serie = df[coluna].dropna()
    if serie.empty:
        return None
    return float(serie.sum()) if agg == "sum" else float(serie.mean())


def _delta_vs_media_historica_agregado(
    df_history: pd.DataFrame,
    value_col: str,
    agg: str,
    run_col: str = "_run_id",
) -> tuple[object, float | None] | None:
    """Mesma ideia de `_delta_vs_media_historica_para_governador`, mas para
    "Todos os Governadores" (ADR 0027): colapsa `df_history` numa única
    linha por execução -- soma (`agg="sum"`, Seguidores) ou média simples
    não ponderada (`agg="mean"`, % engajamento/NSM) de `value_col` entre
    TODOS os governadores presentes naquela execução -- ANTES de comparar
    contra a média histórica, via `compare_vs_historical_average` (mesma
    primitiva de comparação da versão de 1 governador, sem duplicar
    lógica).

    Risco aceito conscientemente (ADR 0027): o conjunto de governadores
    presentes em `df_history` pode mudar entre execuções (cobertura de
    coleta) -- a série agregada por SOMA (Seguidores) pode subir/cair só
    por isso, não por crescimento real de audiência. Não corrigido aqui
    (exigiria alinhar por cohort fixo entre execuções) -- ver ADR 0027,
    "Opções consideradas"."""
    if df_history.empty or not {run_col, value_col}.issubset(df_history.columns):
        return None
    colapsado = (
        df_history.groupby(run_col, as_index=False)[value_col]
        .agg(agg)
        .assign(_chave_agregada=TODOS_OS_GOVERNADORES)
    )
    resultado = compare_vs_historical_average(
        colapsado, value_col=value_col, key_col="_chave_agregada", run_col=run_col
    )
    if resultado is None:
        return None
    return resultado.get(TODOS_OS_GOVERNADORES)


def _proporcao_confiavel(df_growth_todos: pd.DataFrame, coluna_confiavel: str) -> tuple[int, int]:
    """`(n_confiaveis, n_total)` de `coluna_confiavel`
    (`cmgr_confiavel`/`retencao_confiavel`) em `df_growth_todos` -- para o
    tooltip agregado de "Todos os Governadores" (ADR 0027) declarar SEMPRE a
    proporção de governadores com histórico confiável, nunca escondida
    atrás de um sufixo "ilustrativo" automático nem de uma exclusão
    silenciosa dos não confiáveis da média. `(0, 0)` se `df_growth_todos`
    estiver vazio ou sem a coluna."""
    if df_growth_todos.empty or coluna_confiavel not in df_growth_todos.columns:
        return (0, 0)
    total = len(df_growth_todos)
    confiaveis = int(df_growth_todos[coluna_confiavel].fillna(False).sum())
    return (confiaveis, total)


def _kpi_crescimento_agregado(
    nome_base: str,
    valor: float | None,
    n_confiaveis: int,
    n_total: int,
) -> tuple[str, str, None, None, str | None]:
    """Mesma forma de `kpi_row` de `_kpi_crescimento`, mas para "Todos os
    Governadores" (ADR 0027): o rótulo NUNCA ganha o sufixo "· ilustrativo"
    automaticamente, e a média NUNCA exclui os governadores com
    `confiavel=False` -- é sempre a média de TODOS os governadores
    disponíveis. O tooltip declara explicitamente a proporção confiável
    (ex.: "18 de 26 perfis com histórico confiável; os demais ainda são
    ilustrativos") -- informa sem esconder nem subestimar quantos perfis
    realmente sustentam o número."""
    help_text = None
    if n_total:
        help_text = (
            f"{n_confiaveis} de {n_total} perfis com histórico confiável "
            "(>= 6 execuções mensais acumuladas); os demais ainda são "
            "ilustrativos."
        )
    return (nome_base, _fmt_pct(valor), None, None, help_text)


# ---------------------------------------------------------------------------
# Evidência histórica de desempenho (ADR 0026 / issue #154) -- migrada
# INTEIRA de `produzir.py` (ADR 0024) para virar a nova "prova" desta tela;
# zero mudança na lógica de agregação (mesmas constantes/funções, só
# realocadas). Ver `dashboard/screens/produzir.py` para o link de volta.
# ---------------------------------------------------------------------------

TIPO_AMBOS = "Ambos"
TIPO_POSTS = "Posts"
TIPO_REELS = "Reels"
_ORDEM_TIPOS_CONTEUDO = [TIPO_AMBOS, TIPO_POSTS, TIPO_REELS]

METRICA_QUANTIDADE = "Quantidade de publicações"
METRICA_CURTIDAS = "Curtidas"
METRICA_COMENTARIOS = "Comentários"
METRICA_VISUALIZACOES = "Visualizações"
_ORDEM_METRICAS = [METRICA_QUANTIDADE, METRICA_CURTIDAS, METRICA_COMENTARIOS, METRICA_VISUALIZACOES]

# `None` (não uma string vazia) sinaliza "sem coluna de métrica" pra
# `aggregate_metric_by_publication_day(..., agg="count")` -- quantidade de
# publicações conta linhas, não soma nenhuma coluna.
_METRICA_PARA_COLUNA = {
    METRICA_QUANTIDADE: None,
    METRICA_CURTIDAS: "likesCount",
    METRICA_COMENTARIOS: "commentsCount",
    # `videoPlayCount` só existe em reels (`SILVER_REELS_SCHEMA`) -- posts de
    # feed puro nunca vão ter essa coluna, degradando pro estado vazio em
    # `_serie_desempenho_por_publicacao` (nunca uma exceção).
    METRICA_VISUALIZACOES: "videoPlayCount",
}


def _conteudo_do_governador_por_tipo(
    df_reels: pd.DataFrame, df_posts: pd.DataFrame, governor_url: str, tipo: str
) -> pd.DataFrame:
    """`DataFrame` combinado (reels e/ou posts de feed, conforme `tipo` --
    um dos `TIPO_*` acima) do governador selecionado, já filtrado por
    `inputUrl` (ADR 0024) -- ou de TODOS os governadores juntos, sem filtro,
    quando `governor_url == TODOS_OS_GOVERNADORES` (ADR 0027 / issue #161):
    `_serie_desempenho_por_publicacao` já soma/conta por dia sobre todas as
    linhas recebidas, então "não filtrar" já produz a soma entre
    governadores esperada, sem lógica de agregação extra aqui. `DataFrame`
    vazio (nunca exceção) se a(s) fonte(s) pedida(s) estiverem vazias ou sem
    match para este governador."""
    fontes = []
    if tipo in (TIPO_REELS, TIPO_AMBOS):
        fontes.append(df_reels)
    if tipo in (TIPO_POSTS, TIPO_AMBOS):
        fontes.append(df_posts)

    partes = [_filtrar_por_governador_ou_todos(df, governor_url) for df in fontes]
    partes = [p for p in partes if not p.empty]
    if not partes:
        return pd.DataFrame()
    return pd.concat(partes, ignore_index=True)


def _serie_desempenho_por_publicacao(df_conteudo: pd.DataFrame, metrica: str) -> pd.DataFrame:
    """Série agregada por dia de publicação (colunas `data`/`valor`) para
    `metrica` (um dos `METRICA_*` acima) -- `ADR 0024`, generaliza a
    agregação por dia já usada no Radar (`aggregate_pct_negative_by_
    publication_day`, ADR 0023) via `aggregate_metric_by_publication_day`.

    Contagem de linhas (`agg="count"`) para `METRICA_QUANTIDADE`, soma
    (`agg="sum"`) para as demais. `DataFrame` vazio (colunas `data`/`valor`,
    nunca exceção) se `df_conteudo` estiver vazio ou sem a coluna da métrica
    pedida -- caso real e esperado quando `metrica == METRICA_VISUALIZACOES`
    e `tipo == TIPO_POSTS` (posts de feed não têm contagem de visualização)."""
    coluna = _METRICA_PARA_COLUNA[metrica]
    agg = "count" if metrica == METRICA_QUANTIDADE else "sum"
    return aggregate_metric_by_publication_day(df_conteudo, metric_col=coluna, agg=agg)


# ---------------------------------------------------------------------------
# KPIs de crescimento (CMGR/retenção) -- ADR 0026 / issue #154
# ---------------------------------------------------------------------------


def _campo_growth(linha_growth: pd.Series | None, col: str) -> object:
    """Valor de `col` em `linha_growth` (a única linha de
    `governor_growth_metrics` já filtrada a 1 governador) -- `None` (nunca
    `KeyError`) se `linha_growth` for `None` (governador sem linha em
    `governor_growth_metrics`, `DataFrame` vazio) ou não tiver `col`."""
    if linha_growth is None or col not in linha_growth:
        return None
    return linha_growth[col]


def _kpi_crescimento(
    nome_base: str,
    valor: float | None,
    confiavel: bool | None,
    motivo: str | None,
) -> tuple[str, str, None, None, str | None]:
    """Monta a entrada de `kpi_row` para um KPI de crescimento (CMGR/retenção,
    de `data.load_growth_metrics()`) -- ADR 0026, user stories 4-5: valor +
    selo de confiabilidade, NUNCA delta (`items[2]=None` sempre -- já são
    métricas de tendência, uma variação de uma taxa seria confusa).

    Rótulo ganha o sufixo "· ilustrativo" e `help_text` ganha `motivo`
    quando `confiavel is False` (mesmo padrão de sufixo + tooltip já usado
    pelo KPI de NSM antes da verificação de 2026-09-19 confirmar o critério
    de aceite contra dado real -- ver ADR 0020) -- `confiavel=None` (sem linha pro governador,
    `load_growth_metrics()` vazio) degrada para rótulo limpo com valor em
    branco, nunca um "ilustrativo" fabricado por falta de dado."""
    pouco_confiavel = confiavel is False
    label = f"{nome_base} · ilustrativo" if pouco_confiavel else nome_base
    help_text = motivo if pouco_confiavel and motivo else None
    return (label, _fmt_pct(valor), None, None, help_text)


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

    # ADR 0026 / issue #154: cabeçalho volta a ser só o seletor de
    # governador -- o filtro de calendário que vivia numa 2ª coluna (ADR
    # 0024) era específico do destaque de negatividade, que saiu desta tela
    # (virou 2ª leitura no Radar de crise, com o próprio filtro dele).
    # ADR 0027 / issue #161: opção "Todos os Governadores" prepende a lista
    # -- só oferecida quando existe pelo menos 1 governador real (o caso
    # "nenhum governador ainda" abaixo continua idêntico, sem essa opção).
    if not options:
        st.selectbox("Governador", options=[_PLACEHOLDER_SEM_GOVERNADOR], disabled=True)
        governor_url = None
    else:
        nomes_exibidos = [_LABEL_TODOS_OS_GOVERNADORES, *options.keys()]
        nome_selecionado = st.selectbox("Governador", options=nomes_exibidos)
        governor_url = (
            TODOS_OS_GOVERNADORES
            if nome_selecionado == _LABEL_TODOS_OS_GOVERNADORES
            else options[nome_selecionado]
        )
    stage_label("Visão do funil inteiro")

    if governor_url is None:
        st.info(
            "Nenhum governador disponível ainda -- rode a pipeline "
            "(`uv run python pipeline.py`) para popular o dashboard."
        )
        footnote()
        return

    is_todos = governor_url == TODOS_OS_GOVERNADORES

    # ---- Dado bruto ----
    df_sentiment_history = data.comments_only(data.load_sentiment_history())
    if not df_sentiment_history.empty and "inputUrl" in df_sentiment_history.columns:
        df_sentiment_history = df_sentiment_history.assign(
            _chave=_normalize_url(df_sentiment_history["inputUrl"])
        )
    df_sentiment_atual = data.comments_only(data.load_sentiment())
    if not df_sentiment_atual.empty and "inputUrl" in df_sentiment_atual.columns:
        df_sentiment_atual = df_sentiment_atual.assign(
            _chave=_normalize_url(df_sentiment_atual["inputUrl"])
        )
    df_engagement_history = data.load_engagement_history()
    if not df_engagement_history.empty and "inputUrl" in df_engagement_history.columns:
        df_engagement_history = df_engagement_history.assign(
            _chave=_normalize_url(df_engagement_history["inputUrl"])
        )
    df_nsm_history = data.load_nsm_history()
    if not df_nsm_history.empty and "inputUrl" in df_nsm_history.columns:
        df_nsm_history = df_nsm_history.assign(_chave=_normalize_url(df_nsm_history["inputUrl"]))
    df_nsm = data.load_nsm()

    # ADR 0027 / issue #161: "Todos os Governadores" agrega por MÉDIA SIMPLES
    # não ponderada (cada governador pesa igual) -- ver docstring das
    # funções `*_agregado`/`*_todos` acima. Fora daí, comportamento idêntico
    # ao de 1 governador (ADR 0025).
    if is_todos:
        prop_positivo_atual = _proporcao_media_por_governador(df_sentiment_atual, "positive")
        prop_negativo_atual = _proporcao_media_por_governador(df_sentiment_atual, "negative")
        resultado_engajamento = _delta_vs_media_historica_agregado(
            df_engagement_history, "% ENGAJAMENTO", agg="mean"
        )
        resultado_seguidores = _delta_vs_media_historica_agregado(
            df_engagement_history, "followersCount", agg="sum"
        )
        resultado_nsm = _delta_vs_media_historica_agregado(df_nsm_history, "nsm", agg="mean")
        resultado_positivo = _delta_janela_publicacao_agregado(df_sentiment_history)
    else:
        df_sentiment_history_governador = _filtrar_por_governador(
            df_sentiment_history, governor_url
        )
        df_sentiment_governador = _filtrar_por_governador(df_sentiment_atual, governor_url)
        prop_positivo_atual = _proporcao_label(df_sentiment_governador, "positive")
        prop_negativo_atual = _proporcao_label(df_sentiment_governador, "negative")
        # ADR 0025: % engajamento/Seguidores/NSM (métricas de PERFIL) comparam
        # vs. média histórica; % positivo (métrica de CONTEÚDO) compara por
        # janela de data de publicação -- ver docstring das duas funções.
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

    # ---- KPIs ----
    if is_todos:
        valor_engajamento = _agregar_metrica_todos(df_engagement, "% ENGAJAMENTO", "mean")
        valor_seguidores = _agregar_metrica_todos(df_engagement, "followersCount", "sum")
        valor_nsm = _agregar_metrica_todos(df_nsm, "nsm", "mean")
    else:
        df_governador_engagement = _filtrar_por_governador(df_engagement, governor_url)
        df_nsm_governador = _filtrar_por_governador(df_nsm, governor_url)
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
                "Engajamento qualificado",
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
                    "engajamento. Validado contra os 27 perfis reais (ADR "
                    "0020, verificação de 2026-09-19): o ranking por NSM "
                    "muda de posição para 25 dos 27 perfis frente ao ranking "
                    "por engajamento bruto."
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

    # ---- KPIs de crescimento (ADR 0026 / issue #154) ----
    # Reaproveita `kpi_row()` como já é (2ª chamada, sem mudar assinatura --
    # user story 15). Nenhum delta: CMGR/retenção já são métricas de
    # tendência.
    st.markdown("##### Crescimento")
    df_growth_todos = data.load_growth_metrics()

    if is_todos:
        # ADR 0027 / issue #161: média simples entre TODOS os governadores
        # disponíveis, sempre -- nunca exclui os `confiavel=False` da média
        # nem ganha o sufixo "· ilustrativo" automaticamente. O tooltip
        # declara a proporção confiável (ver `_kpi_crescimento_agregado`).
        valor_cmgr = _agregar_metrica_todos(df_growth_todos, "cmgr", "mean")
        valor_retencao = _agregar_metrica_todos(df_growth_todos, "retencao", "mean")
        n_confiaveis_cmgr, n_total_cmgr = _proporcao_confiavel(df_growth_todos, "cmgr_confiavel")
        n_confiaveis_ret, n_total_ret = _proporcao_confiavel(
            df_growth_todos, "retencao_confiavel"
        )
        kpi_row(
            [
                _kpi_crescimento_agregado("CMGR", valor_cmgr, n_confiaveis_cmgr, n_total_cmgr),
                _kpi_crescimento_agregado(
                    "Retenção", valor_retencao, n_confiaveis_ret, n_total_ret
                ),
            ]
        )
    else:
        df_growth = _filtrar_por_governador(df_growth_todos, governor_url)
        linha_growth = df_growth.iloc[0] if not df_growth.empty else None

        kpi_row(
            [
                _kpi_crescimento(
                    "CMGR",
                    _campo_growth(linha_growth, "cmgr"),
                    _campo_growth(linha_growth, "cmgr_confiavel"),
                    _campo_growth(linha_growth, "cmgr_motivo"),
                ),
                _kpi_crescimento(
                    "Retenção",
                    _campo_growth(linha_growth, "retencao"),
                    _campo_growth(linha_growth, "retencao_confiavel"),
                    _campo_growth(linha_growth, "retencao_motivo"),
                ),
            ]
        )

    # ---- Evidência histórica de desempenho (prova -- ADR 0021/0026) ----
    # Migrada inteira de "O que produzir" (ADR 0024) -- zero mudança na
    # lógica de agregação, só realocação (ver docstring do módulo).
    # Layout ADR 0027 / issue #161: gráfico em 75% da largura à esquerda,
    # os 3 filtros (Tipo, Métrica, Período) empilhados numa coluna de 25% à
    # direita -- os widgets são criados na ordem em que o valor deles é
    # necessário (Tipo/Métrica antes de calcular a série; Período só depois
    # de conhecer `data_min`/`data_max` da série), mas cada `with` aponta
    # pro container certo, então a ordem VISUAL (gráfico à esquerda, filtros
    # à direita) não depende da ordem de execução do código.
    st.markdown("#### Evidência histórica de desempenho")
    col_grafico, col_filtros = st.columns([0.75, 0.25])

    # `load_reels_content()`/`load_posts_content()` retornam TODOS os 27
    # perfis -- `_conteudo_do_governador_por_tipo` filtra por `governor_url`
    # internamente (ou agrega todos, se `is_todos` -- ver sua docstring).
    df_reels_conteudo = data.load_reels_content()
    df_posts_conteudo = data.load_posts_content()

    with col_filtros:
        tipo_selecionado = st.selectbox(
            "Tipo de conteúdo", options=_ORDEM_TIPOS_CONTEUDO, key="resumo_tipo_conteudo"
        )
        metrica_selecionada = st.selectbox(
            "Métrica", options=_ORDEM_METRICAS, key="resumo_metrica_desempenho"
        )

    df_conteudo = _conteudo_do_governador_por_tipo(
        df_reels_conteudo, df_posts_conteudo, governor_url, tipo_selecionado
    )
    df_serie_completa = _serie_desempenho_por_publicacao(df_conteudo, metrica_selecionada)

    if df_serie_completa.empty:
        with col_grafico:
            st.caption(
                "Sem dado disponível para essa combinação de tipo de conteúdo e "
                "métrica ainda -- comum quando \"Visualizações\" é escolhida com "
                "\"Posts\" (posts de feed não têm contagem de visualização)."
            )
    else:
        data_min = df_serie_completa["data"].min()
        data_max = df_serie_completa["data"].max()
        with col_filtros:
            intervalo = st.date_input(
                "Período (data de publicação)",
                value=(data_min, data_max),
                min_value=data_min,
                max_value=data_max,
                key="resumo_intervalo_desempenho",
            )
        data_inicio, data_fim = normalize_date_input_range(intervalo)
        df_serie = filter_by_date_range(df_serie_completa, "data", data_inicio, data_fim)

        with col_grafico:
            if df_serie.empty:
                st.caption("Nenhuma publicação no período selecionado.")
            else:
                fig = go.Figure()
                for segmento in quebrar_em_segmentos(df_serie):
                    fig.add_trace(
                        go.Scatter(
                            x=segmento["data"],
                            y=segmento["valor"],
                            mode="lines+markers",
                            line={"color": COLORS["muted"]},
                            marker={"color": COLORS["muted"], "size": 6},
                            showlegend=False,
                        )
                    )
                fig.update_layout(
                    yaxis_title=metrica_selecionada,
                    xaxis_title="Data de publicação",
                    showlegend=False,
                    margin={"t": 30, "b": 10},
                )
                st.plotly_chart(fig, use_container_width=True)

    footnote()
