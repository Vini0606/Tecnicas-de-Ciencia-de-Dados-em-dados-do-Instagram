"""Sub-aba NSM do Resumo (ADR 0031 / issue #183) -- provisória nesta fatia.

Recebe, sem alteração de comportamento, a frase de decisão semafórica e as
linhas de KPIs (4 existentes + 2 de crescimento) que o Resumo tinha antes de
virar contêiner de sub-abas. A issue #187 redesenha esta sub-aba.

Toda a lógica de decisão vive em funções puras nomeadas abaixo, testadas em
`tests/test_dashboard_screens_resumo_nsm.py`; `render()` só orquestra I/O do
Streamlit sobre o resultado dessas funções.
"""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from dashboard.core import data
from dashboard.core.components import decision_band, kpi_row
from dashboard.core.deltas import (
    LIMIAR_NEGATIVIDADE_ALERTA,
    compare_publication_window,
    compare_vs_historical_average,
)
from dashboard.screens.resumo_comum import (
    _PLACEHOLDER_SEM_GOVERNADOR,
    TODOS_OS_GOVERNADORES,
    _filtrar_por_governador,
    _normalize_url,
)

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
        return (
            "Boa semana: % positivo e % de engajamento subiram vs. a coleta anterior."
        )
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
        _is_positive=(
            df_sentiment_history_governador["sentiment_label"] == "positive"
        ).astype(float)
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


def _proporcao_media_por_governador(
    df_comments_todos: pd.DataFrame, label: str
) -> float | None:
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
    if df_sentiment_history_todos.empty or not {"sentiment_label", "_chave"}.issubset(
        df_sentiment_history_todos.columns
    ):
        return None
    df = df_sentiment_history_todos.assign(
        _is_positive=(
            df_sentiment_history_todos["sentiment_label"] == "positive"
        ).astype(float)
    )
    resultado = compare_publication_window(
        df, value_col="_is_positive", key_col="_chave"
    )
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


def _proporcao_confiavel(
    df_growth_todos: pd.DataFrame, coluna_confiavel: str
) -> tuple[int, int]:
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
# Contraste de rankings bruto x NSM (issue #187)
#
# "Engajamento bruto" = `total_engajamento` de `governor_nsm` (volume total de
# curtidas + comentarios por perfil, a mesma coluna-fonte `TOTAL ENGAJAMENTO`
# de `governor_engagement`). A medida exata usada na verificacao da ADR 0020
# nao e identificavel com seguranca (o texto da ADR cita "volume bruto"); o
# volume total e a leitura direta. Contra o dado de 2026-10-04 o ranking por
# NSM diverge desse bruto em 20 de 26 perfis.
#
# O NSM de `governor_nsm` e uma razao sem teto (proporcao positiva x alcance
# medio); para exibi-lo de 0 a 100 aplicamos min-max entre os perfis com NSM
# (mesma normalizacao do Scorecard, ADR 0030): 100 = lider, 0 = ultimo.
# ---------------------------------------------------------------------------

TOP_N = 10
ETIQUETA_SUBIU = "SUBIU"
ETIQUETA_CAIU = "CAIU"


def _indice_nsm_0_100(nsm: pd.Series) -> pd.Series:
    """NSM bruto -> 0-100 por min-max entre os perfis com valor. Todos
    iguais (ou so um perfil) -> 100 para quem tem valor; `NaN` preservado."""
    validos = nsm.dropna()
    if validos.empty:
        return nsm.astype(float)
    menor, maior = validos.min(), validos.max()
    if maior == menor:
        return nsm.where(nsm.isna(), 100.0).astype(float)
    return (nsm - menor) / (maior - menor) * 100.0


def montar_tabela_contraste(
    df_nsm: pd.DataFrame,
    df_comentarios: pd.DataFrame,
    df_metadata: pd.DataFrame,
) -> pd.DataFrame:
    """Uma linha por perfil de `governor_nsm`, colunas `chave`, `nome`,
    `bruto`, `nsm` (0-100, `NaN` = perfil sem NSM), `pct_pos`, `pct_neg`
    (fracoes 0-1 dos comentarios; `NaN` sem comentarios). Vazio (com as
    colunas) se `df_nsm` estiver vazio ou sem as colunas esperadas."""
    colunas = ["chave", "nome", "bruto", "nsm", "pct_pos", "pct_neg"]
    if df_nsm.empty or not {"inputUrl", "nsm"}.issubset(df_nsm.columns):
        return pd.DataFrame(columns=colunas)

    nan = pd.Series(float("nan"), index=df_nsm.index)
    tabela = pd.DataFrame(
        {
            "chave": _normalize_url(df_nsm["inputUrl"]),
            "nome": df_nsm["username"] if "username" in df_nsm.columns else nan,
            "bruto": (
                df_nsm["total_engajamento"].astype(float)
                if "total_engajamento" in df_nsm.columns
                else nan
            ),
            "nsm": _indice_nsm_0_100(df_nsm["nsm"].astype(float)),
        }
    )

    if not df_metadata.empty and {"inputUrl", "nome"}.issubset(df_metadata.columns):
        nomes = dict(
            zip(
                _normalize_url(df_metadata["inputUrl"]),
                df_metadata["nome"],
                strict=True,
            )
        )
        tabela["nome"] = [
            nomes[c] if isinstance(nomes.get(c), str) and nomes[c] else n
            for c, n in zip(tabela["chave"], tabela["nome"], strict=True)
        ]
    tabela["nome"] = tabela["nome"].fillna(tabela["chave"]).astype(str)

    for coluna, label in (("pct_pos", "positive"), ("pct_neg", "negative")):
        tabela[coluna] = float("nan")
        if not df_comentarios.empty and {"inputUrl", "sentiment_label"}.issubset(
            df_comentarios.columns
        ):
            chaves = _normalize_url(df_comentarios["inputUrl"])
            frac = (df_comentarios["sentiment_label"] == label).groupby(chaves).mean()
            tabela[coluna] = tabela["chave"].map(frac)
    # `linhas_ranking` indexa por `chave`: defensivo contra URL repetida.
    return (tabela[colunas].drop_duplicates(subset="chave", keep="first")).reset_index(
        drop=True
    )


def extremo(
    tabela: pd.DataFrame, coluna: str, maior: bool = True
) -> tuple[str, float] | None:
    """`(nome, valor)` do perfil de maior (ou menor) `coluna`; empate decidido
    pelo nome em ordem alfabetica (deterministico). `None` se nao ha valor."""
    if tabela.empty or coluna not in tabela.columns:
        return None
    validos = tabela.dropna(subset=[coluna])
    if validos.empty:
        return None
    ordenado = validos.sort_values(
        [coluna, "nome"], ascending=[not maior, True], kind="mergesort"
    )
    linha = ordenado.iloc[0]
    return str(linha["nome"]), float(linha[coluna])


def posicoes(tabela: pd.DataFrame, coluna: str) -> dict[str, int]:
    """`{chave: posicao}` (1 = maior `coluna`) no ranking COMPLETO; empates
    desempatados pelo nome. Perfis sem valor ficam de fora."""
    if tabela.empty or coluna not in tabela.columns:
        return {}
    validos = tabela.dropna(subset=[coluna]).sort_values(
        [coluna, "nome"], ascending=[False, True], kind="mergesort"
    )
    return {chave: i for i, chave in enumerate(validos["chave"], start=1)}


def etiqueta_mudanca(pos_bruto: int | None, pos_nsm: int | None) -> str | None:
    """`SUBIU` se a posicao no ranking por NSM e melhor (menor) que no bruto,
    `CAIU` se pior, `None` se igual ou se faltar uma das posicoes."""
    if pos_bruto is None or pos_nsm is None or pos_bruto == pos_nsm:
        return None
    return ETIQUETA_SUBIU if pos_nsm < pos_bruto else ETIQUETA_CAIU


def linhas_ranking(
    tabela: pd.DataFrame,
    coluna: str,
    chave_selecionada: str | None,
    com_etiqueta: bool = False,
    n: int = TOP_N,
) -> list[dict]:
    """Linhas do ranking por `coluna`: os `n` primeiros mais, se o governador
    selecionado (`chave_selecionada`, `None` = "Todos") estiver fora do top
    `n` e tiver posicao, uma linha extra com `extra=True` e a posicao real.
    Cada linha: `posicao`, `nome`, `valor`, `selecionado`, `etiqueta`,
    `extra`. A etiqueta SUBIU/CAIU (so com `com_etiqueta=True`) compara as
    posicoes nos rankings completos por `bruto` e `nsm`."""
    pos = posicoes(tabela, coluna)
    if not pos:
        return []
    pos_bruto = posicoes(tabela, "bruto")
    pos_nsm = posicoes(tabela, "nsm")
    por_chave = tabela.set_index("chave")

    def linha(chave: str, extra: bool) -> dict:
        reg = por_chave.loc[chave]
        return {
            "posicao": pos[chave],
            "nome": str(reg["nome"]),
            "valor": float(reg[coluna]),
            "selecionado": chave == chave_selecionada,
            "etiqueta": (
                etiqueta_mudanca(pos_bruto.get(chave), pos_nsm.get(chave))
                if com_etiqueta
                else None
            ),
            "extra": extra,
        }

    ordenadas = sorted(pos, key=pos.__getitem__)
    linhas = [linha(c, False) for c in ordenadas[:n]]
    if chave_selecionada in pos and pos[chave_selecionada] > n:
        linhas.append(linha(chave_selecionada, True))
    return linhas


def valor_cartao_nsm(
    tabela: pd.DataFrame, chave_selecionada: str | None
) -> float | None:
    """NSM (0-100) do selecionado, ou a media simples dos perfis com NSM em
    "Todos" (`chave_selecionada=None`). `None` sem dado."""
    if tabela.empty or "nsm" not in tabela.columns:
        return None
    if chave_selecionada is None:
        serie = tabela["nsm"].dropna()
        return float(serie.mean()) if not serie.empty else None
    linha = tabela[tabela["chave"] == chave_selecionada]["nsm"].dropna()
    return float(linha.iloc[0]) if not linha.empty else None


# Tokens de cor de dado (claro, escuro): azul/verde/vermelho reaproveitados
# dos tokens validados com a skill `dataviz` no Funil (superficies #fcfcfb /
# #1a1a19). Etiquetas e valores sempre tem texto, nunca so cor.
_AZUL = ("#2a78d6", "#5a9df0")
_VERDE = ("#008300", "#3fae3f")
_VERMELHO = ("#a32d2d", "#e66767")


def _vars_cor(i: int) -> str:
    return f"--n-azul:{_AZUL[i]};--n-verde:{_VERDE[i]};--n-verm:{_VERMELHO[i]};"


_CSS_NSM = (
    "<style>"
    f".nsm-viz {{ {_vars_cor(0)} --n-trilho: rgba(128,128,128,.18); }}"
    "@media (prefers-color-scheme: dark) {"
    f' :root:where(:not([data-theme="light"])) .nsm-viz {{ {_vars_cor(1)} }} }}'
    f':root[data-theme="dark"] .nsm-viz {{ {_vars_cor(1)} }}'
    """
.nsm-viz .n-cards { display: flex; gap: 12px; flex-wrap: wrap; margin: 8px 0 18px; }
.nsm-viz .n-card { flex: 1 1 200px; border: 1px solid var(--n-trilho); border-radius: 10px;
  padding: 12px 16px; }
.nsm-viz .n-card.verde { border-left: 4px solid var(--n-verde); }
.nsm-viz .n-card.verm { border-left: 4px solid var(--n-verm); }
.nsm-viz .n-card-t { font-size: 12px; opacity: .75; }
.nsm-viz .n-card-v { font-size: 26px; font-weight: 500; }
.nsm-viz .n-card.verde .n-card-v { color: var(--n-verde); }
.nsm-viz .n-card.verm .n-card-v { color: var(--n-verm); }
.nsm-viz .n-card-s { font-size: 13px; opacity: .85; }
.nsm-viz .n-linha { display: flex; align-items: center; gap: 8px; margin: 4px 0;
  font-size: 13px; padding: 2px 6px; border-radius: 6px; }
.nsm-viz .n-linha.sel { outline: 2px solid currentColor; font-weight: 600; }
.nsm-viz .n-linha.extra { margin-top: 10px; }
.nsm-viz .n-pos { width: 28px; text-align: right; opacity: .7; }
.nsm-viz .n-nome { width: 150px; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; }
.nsm-viz .n-trilho { flex: 1; background: var(--n-trilho); border-radius: 4px; height: 16px; }
.nsm-viz .n-barra { height: 16px; border-radius: 4px; }
.nsm-viz .n-barra.azul { background: var(--n-azul); }
.nsm-viz .n-barra.verde { background: var(--n-verde); }
.nsm-viz .n-val { width: 64px; text-align: right; }
.nsm-viz .n-et { font-size: 11px; border-radius: 6px; padding: 0 6px; min-width: 56px;
  text-align: center; border: 1px solid currentColor; }
.nsm-viz .n-et.subiu { color: var(--n-verde); }
.nsm-viz .n-et.caiu { color: var(--n-verm); }
.nsm-viz .n-sel-tag { font-size: 11px; opacity: .8; }
</style>"""
)


def _html_cartao(titulo: str, valor: str, sub: str, tom: str | None) -> str:
    return (
        f'<div class="n-card {tom or ""}"><div class="n-card-t">{html.escape(titulo)}'
        f'</div><div class="n-card-v">{html.escape(valor)}</div>'
        f'<div class="n-card-s">{html.escape(sub)}</div></div>'
    )


def _html_ranking(linhas: list[dict], cor: str, fmt) -> str:
    if not linhas:
        return "<div>Sem dados.</div>"
    maximo = max(item["valor"] for item in linhas) or 1.0
    partes = []
    for item in linhas:
        largura = max(2.0, item["valor"] / maximo * 100.0) if item["valor"] > 0 else 0.0
        et = ""
        if item["etiqueta"]:
            seta = "▲" if item["etiqueta"] == ETIQUETA_SUBIU else "▼"
            et = (
                f'<span class="n-et {item["etiqueta"].lower()}">'
                f"{seta} {item['etiqueta']}</span>"
            )
        tag = (
            ' <span class="n-sel-tag">(selecionado)</span>'
            if item["selecionado"]
            else ""
        )
        classes = "n-linha" + (" sel" if item["selecionado"] else "")
        classes += " extra" if item["extra"] else ""
        nome = html.escape(item["nome"])
        partes.append(
            f'<div class="{classes}"><span class="n-pos">{item["posicao"]}º</span>'
            f'<span class="n-nome" title="{nome}">{nome}{tag}</span>'
            f'<span class="n-trilho"><div class="n-barra {cor}" '
            f'style="width:{largura:.1f}%"></div></span>'
            f'<span class="n-val">{fmt(item["valor"])}</span>{et}</div>'
        )
    return "".join(partes)


def _fmt_nsm_0_100(valor: float | None) -> str:
    if valor is None or pd.isna(valor):
        return _PLACEHOLDER_SEM_GOVERNADOR
    return f"{valor:.1f}"


def _render_contraste(governor_url: str, is_todos: bool) -> None:
    tabela = montar_tabela_contraste(
        data.load_nsm(),
        data.comments_only(data.load_sentiment()),
        data.load_governors_metadata(),
    )
    chave = None if is_todos else _normalize_url(pd.Series([governor_url])).iloc[0]

    st.markdown("### North Star Metric — Engajamento Positivo Qualificado")
    st.markdown(
        "A métrica-norte mede valor entregue (aprovação real), não esforço. "
        "O contraste abaixo mostra que alto engajamento não é alta aprovação."
    )
    if tabela.empty:
        st.info("Ainda não há dados de engajamento qualificado.")
        return

    valor = valor_cartao_nsm(tabela, chave)
    melhor = extremo(tabela, "pct_pos", maior=True)
    pior = extremo(tabela, "pct_neg", maior=True)
    cartoes = [
        _html_cartao(
            "Engajamento qualificado" + (" (média dos perfis)" if is_todos else ""),
            _fmt_nsm_0_100(valor),
            "índice de 0 a 100",
            "verde",
        ),
        _html_cartao(
            "Melhor aprovação",
            _fmt_pct(melhor[1]) if melhor else _PLACEHOLDER_SEM_GOVERNADOR,
            melhor[0] if melhor else "sem comentários",
            None,
        ),
        _html_cartao(
            "Maior rejeição",
            _fmt_pct(pior[1]) if pior else _PLACEHOLDER_SEM_GOVERNADOR,
            pior[0] if pior else "sem comentários",
            "verm",
        ),
    ]
    esq = linhas_ranking(tabela, "bruto", chave)
    dir_ = linhas_ranking(tabela, "nsm", chave, com_etiqueta=True)
    st.markdown(
        f'{_CSS_NSM}<div class="nsm-viz"><div class="n-cards">{"".join(cartoes)}</div>'
        '<div style="display:flex;gap:24px;flex-wrap:wrap;">'
        '<div style="flex:1 1 360px;"><strong>Por engajamento bruto</strong>'
        f"{_html_ranking(esq, 'azul', _fmt_int_br)}</div>"
        '<div style="flex:1 1 360px;"><strong>Por engajamento qualificado</strong>'
        f"{_html_ranking(dir_, 'verde', _fmt_nsm_0_100)}</div>"
        "</div></div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Engajamento bruto = total de curtidas e comentários por perfil. "
        "SUBIU/CAIU compara a posição no ranking qualificado com a do bruto."
    )


# ---------------------------------------------------------------------------
# render()
# ---------------------------------------------------------------------------


def render(governor_url: str) -> None:
    """Renderiza a sub-aba NSM para `governor_url` (URL real ou
    `TODOS_OS_GOVERNADORES`)."""
    df_engagement = data.load_engagement()
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
        df_nsm_history = df_nsm_history.assign(
            _chave=_normalize_url(df_nsm_history["inputUrl"])
        )
    df_nsm = data.load_nsm()

    # ADR 0027 / issue #161: "Todos os Governadores" agrega por MÉDIA SIMPLES
    # não ponderada (cada governador pesa igual) -- ver docstring das
    # funções `*_agregado`/`*_todos` acima. Fora daí, comportamento idêntico
    # ao de 1 governador (ADR 0025).
    if is_todos:
        prop_positivo_atual = _proporcao_media_por_governador(
            df_sentiment_atual, "positive"
        )
        prop_negativo_atual = _proporcao_media_por_governador(
            df_sentiment_atual, "negative"
        )
        resultado_engajamento = _delta_vs_media_historica_agregado(
            df_engagement_history, "% ENGAJAMENTO", agg="mean"
        )
        resultado_seguidores = _delta_vs_media_historica_agregado(
            df_engagement_history, "followersCount", agg="sum"
        )
        resultado_nsm = _delta_vs_media_historica_agregado(
            df_nsm_history, "nsm", agg="mean"
        )
        resultado_positivo = _delta_janela_publicacao_agregado(df_sentiment_history)
    else:
        df_sentiment_history_governador = _filtrar_por_governador(
            df_sentiment_history, governor_url
        )
        df_sentiment_governador = _filtrar_por_governador(
            df_sentiment_atual, governor_url
        )
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
        valor_engajamento = _agregar_metrica_todos(
            df_engagement, "% ENGAJAMENTO", "mean"
        )
        valor_seguidores = _agregar_metrica_todos(
            df_engagement, "followersCount", "sum"
        )
        valor_nsm = _agregar_metrica_todos(df_nsm, "nsm", "mean")
    else:
        df_governador_engagement = _filtrar_por_governador(df_engagement, governor_url)
        df_nsm_governador = _filtrar_por_governador(df_nsm, governor_url)
        valor_engajamento = (
            df_governador_engagement["% ENGAJAMENTO"].iloc[0]
            if not df_governador_engagement.empty
            and "% ENGAJAMENTO" in df_governador_engagement
            else None
        )
        valor_seguidores = (
            df_governador_engagement["followersCount"].iloc[0]
            if not df_governador_engagement.empty
            and "followersCount" in df_governador_engagement
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
                _fmt_delta_pct(
                    resultado_seguidores[1] if resultado_seguidores else None
                ),
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
        n_confiaveis_cmgr, n_total_cmgr = _proporcao_confiavel(
            df_growth_todos, "cmgr_confiavel"
        )
        n_confiaveis_ret, n_total_ret = _proporcao_confiavel(
            df_growth_todos, "retencao_confiavel"
        )
        kpi_row(
            [
                _kpi_crescimento_agregado(
                    "CMGR", valor_cmgr, n_confiaveis_cmgr, n_total_cmgr
                ),
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

    _render_contraste(governor_url, is_todos)
