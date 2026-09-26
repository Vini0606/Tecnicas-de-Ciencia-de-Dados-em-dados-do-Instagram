"""Cálculo de variação vs. execução anterior (ADR 0021 / issue #110).

Chamado "run-over-run" no conceito, não "semana-a-semana": o pipeline não
tem agendamento fixo hoje (execuções são manuais/ad hoc -- o agendamento via
lambda AWS é item pendente, ver ADR 0021, ponto de atrito 4), então "última
execução vs. anterior" pode significar dias ou meses de intervalo, nunca uma
semana garantida. O nome público `week_over_week` é mantido por brevidade
(mesma decisão da issue #110) -- o que importa é o comportamento abaixo, não
o nome da função.
"""

from __future__ import annotations

import os

import pandas as pd
from dotenv import load_dotenv

# Primeira leitura de `.env` pelo pacote `dashboard/` (ADR 0025 / issue
# #153) -- decisão explícita de manter a variável abaixo lida aqui, não em
# `config/settings.py`, para preservar a autocontenção do pacote do
# dashboard já estabelecida pela ADR 0021 (nenhuma dependência cruzada
# dashboard -> `config/`).
load_dotenv()

# Limiar de alerta de negatividade (ADR 0021 / issue #111). Definido aqui, e
# não em `dashboard/screens/radar.py`, porque a Tela 1 ("Resumo da semana",
# issue #111) precisa dele para a faixa de decisão semafórica ANTES da Tela 3
# ("Radar de crise", issue #113) existir -- ver issue #111, user story 3
# ("mesmo critério da Tela 3"). Quando a issue #113 for implementada, ela
# deve IMPORTAR esta constante (`from dashboard.core.deltas import
# LIMIAR_NEGATIVIDADE_ALERTA`), nunca redefinir um segundo valor: as duas
# telas precisam concordar sobre o que conta como "crise" sem exigir que a
# analista de assessoria memorize dois números diferentes para o mesmo
# conceito.
#
# 0.30 (30% dos comentários avaliados como negativos) é um ponto de partida
# documentado, não calibrado contra dado real: o projeto ainda não acumulou
# histórico suficiente para justificar um limiar orientado a dado (mesma
# limitação já registrada para CMGR/retenção em `governor_growth_metrics`,
# ver `GOLD_GROWTH_METRICS_SCHEMA` / ADR 0020 Ficha 7). Escolhido por ser
# redondo e fácil de explicar ("quase 1 em cada 3 comentários é negativo") --
# revisar quando a Tela 3 tiver dado real suficiente para recalibrar.
LIMIAR_NEGATIVIDADE_ALERTA = 0.30

JANELA_ALERTA_NEGATIVIDADE_DIAS = int(os.environ.get("JANELA_ALERTA_NEGATIVIDADE_DIAS", 7))
"""Tamanho (em dias) da janela móvel ancorada na data de PUBLICAÇÃO usada por
`compare_publication_window` (ADR 0025 / issue #153) -- substitui a
comparação por execução (`week_over_week`) para métricas de CONTEÚDO
(curtidas, comentários, visualizações, % positivo/negativo de comentário):
o pipeline não tem cadência fixa (ADR 0021, ponto de atrito 4), então
"execução atual vs. anterior" podia significar um dia ou vários meses de
intervalo. Configurável via `.env` (`JANELA_ALERTA_NEGATIVIDADE_DIAS`,
padrão 7) -- ver `.env.example`. Só o ramo "warn" do Radar de crise usa esta
janela para o critério de alerta; o ramo "danger" continua um limiar
absoluto (`LIMIAR_NEGATIVIDADE_ALERTA`), sem mudança."""


def week_over_week(
    df_history: pd.DataFrame,
    value_col: str,
    key_col: str = "inputUrl",
    run_col: str = "_run_id",
) -> dict[object, tuple[object, float | None]] | None:
    """Compara as 2 execuções mais recentes de `df_history` por `run_col`,
    pivotando por `key_col`. Retorna `{chave: (valor_atual, delta_percentual)}`.

    - Retorna `None` se houver menos de 2 execuções no histórico -- a tela
      deve ocultar a seta de variação nesse caso, nunca mostrar "0%".
    - Uma chave ausente na execução anterior, ou com valor anterior nulo/zero
      (divisão por zero), recebe `delta_percentual=None` -- documentado,
      nunca levanta exceção.
    """
    if df_history.empty or run_col not in df_history.columns:
        return None

    runs = sorted(df_history[run_col].unique())
    if len(runs) < 2:
        return None
    atual_id, anterior_id = runs[-1], runs[-2]

    serie_atual = (
        df_history[df_history[run_col] == atual_id]
        .drop_duplicates(subset=[key_col], keep="last")
        .set_index(key_col)[value_col]
    )
    serie_anterior = (
        df_history[df_history[run_col] == anterior_id]
        .drop_duplicates(subset=[key_col], keep="last")
        .set_index(key_col)[value_col]
    )

    resultado: dict[object, tuple[object, float | None]] = {}
    for chave, valor_atual in serie_atual.items():
        if chave not in serie_anterior.index:
            resultado[chave] = (valor_atual, None)
            continue
        valor_anterior = serie_anterior.loc[chave]
        if pd.isna(valor_anterior) or valor_anterior == 0:
            resultado[chave] = (valor_atual, None)
            continue
        delta_percentual = (valor_atual - valor_anterior) / valor_anterior * 100
        resultado[chave] = (valor_atual, delta_percentual)
    return resultado


def compare_publication_window(
    df: pd.DataFrame,
    value_col: str,
    key_col: str | None = None,
    timestamp_col: str = "timestamp",
    window_days: int = JANELA_ALERTA_NEGATIVIDADE_DIAS,
    agg: str = "mean",
) -> dict[object, tuple[float, float | None, float | None]] | None:
    """Compara os `window_days` dias de PUBLICAÇÃO mais recentes COM PELO
    MENOS 1 LINHA DE DADO ("janela atual") contra os `window_days` dias com
    dado imediatamente anteriores a esses ("janela anterior") -- ADR 0027,
    substitui o critério anterior (ADR 0025 / issue #153), que ancorava em
    CALENDÁRIO (`maior_data - window_days` dias corridos).

    Por que mudar de calendário para disponibilidade: o pipeline não roda com
    cadência fixa (ADR 0021, ponto de atrito 4) -- um corte de calendário
    fixo sobre a data de publicação ainda assumia uma cadência mínima de
    postagem que a maioria dos perfis reais não tem (medido: 18 de 25
    governadores ficavam sem nenhum dado na janela anterior de calendário,
    mesmo tendo publicações mais antigas reais para comparar). Agrupar por
    DIAS DISTINTOS COM DADO (ignorando buracos de coleta, sem limite de
    tamanho) resolve isso sem inventar um conceito novo -- é a mesma
    generalização que a ADR 0025 já tinha aplicado ao trocar EXECUÇÃO por
    PUBLICAÇÃO, uma camada mais fundo.

    **Janela assimétrica aceita deliberadamente:** se existirem menos de
    `window_days` dias-com-dado ANTES da janela atual, a janela anterior usa
    quantos existirem (>= 1) -- nunca exige um "piso mínimo" de dias. Prioriza
    sempre mostrar uma seta de variação (aceitando que ela fique mais
    ruidosa em histórico curto) a esconder a comparação. `delta_percentual`
    só vira `None` por falta de janela anterior quando NÃO EXISTE nenhum dia
    anterior com dado -- o único caso em que de fato não há nada para
    comparar.

    Generaliza o critério que antes vivia só em
    `radar.py::_tema_maior_alta_negatividade` (comparação por execução via
    `week_over_week`) para que Resumo (`% positivo`) e Radar (tema em maior
    ascensão de negatividade) compartilhem a mesma primitiva -- métricas de
    CONTEÚDO têm data de publicação real por linha, diferente das métricas
    de PERFIL (ver `compare_vs_historical_average`).

    `key_col=None` (default) trata `df` inteiro como um único grupo -- o
    resultado tem uma única entrada sob a chave `None` (uso do Resumo, já
    filtrado a 1 governador). Com `key_col`, uma entrada por valor distinto
    dessa coluna (uso do Radar, `key_col="Topic"`) -- os dias-com-dado que
    definem as duas janelas são calculados sobre `df` INTEIRO (todas as
    chaves juntas), não por chave: garante que todo tema seja comparado nas
    MESMAS duas janelas, senão temas com cadências diferentes ficariam
    incomparáveis entre si. `agg` agrega `value_col` dentro de cada janela
    (`"mean"` para proporção, `"sum"` para contagem/soma).

    Retorna `{chave: (valor_atual, delta_percentual, valor_anterior)}`.
    `None` (nunca exceção) se `df` estiver vazio, faltar coluna obrigatória,
    ou não houver nenhuma linha com data parseável -- não há o que comparar.
    Por chave, `delta_percentual=None` (nunca um delta fabricado) se a chave
    não tiver dado na janela anterior, ou se o valor da janela anterior for
    nulo/zero (divisão por zero) -- mesma convenção de degradação graciosa de
    `week_over_week`."""
    required = {value_col, timestamp_col} | ({key_col} if key_col else set())
    if df.empty or not required.issubset(df.columns):
        return None

    dados = df.assign(
        _data=parse_publication_dates(df, timestamp_col=timestamp_col)
    ).dropna(subset=["_data"])
    if dados.empty:
        return None

    dias_distintos = sorted(dados["_data"].unique())
    dias_atual = dias_distintos[-window_days:]
    # Slice negativo já devolve `[]` quando há `window_days` dias ou menos no
    # total (nada sobra antes da janela atual) -- sem precisar de um `if`
    # explícito para esse caso.
    dias_anterior = dias_distintos[-(2 * window_days) : -window_days]

    janela_atual = dados[dados["_data"].isin(dias_atual)]
    janela_anterior = dados[dados["_data"].isin(dias_anterior)]
    if janela_atual.empty:
        return None

    def _agregar(subset: pd.DataFrame) -> pd.Series:
        if key_col:
            return subset.groupby(key_col)[value_col].agg(agg)
        return pd.Series({None: subset[value_col].agg(agg)})

    serie_atual = _agregar(janela_atual)
    serie_anterior = (
        _agregar(janela_anterior) if not janela_anterior.empty else pd.Series(dtype="float64")
    )

    resultado: dict[object, tuple[float, float | None, float | None]] = {}
    for chave, valor_atual in serie_atual.items():
        if chave not in serie_anterior.index:
            resultado[chave] = (valor_atual, None, None)
            continue
        valor_anterior = serie_anterior.loc[chave]
        if pd.isna(valor_anterior) or valor_anterior == 0:
            resultado[chave] = (valor_atual, None, valor_anterior)
            continue
        delta_percentual = (valor_atual - valor_anterior) / valor_anterior * 100
        resultado[chave] = (valor_atual, delta_percentual, valor_anterior)
    return resultado


def compare_vs_historical_average(
    df_history: pd.DataFrame,
    value_col: str,
    key_col: str = "inputUrl",
    run_col: str = "_run_id",
) -> dict[object, tuple[object, float | None]] | None:
    """Compara o valor da execução mais recente de cada chave contra a MÉDIA
    de todos os valores de execuções ANTERIORES daquela chave (ADR 0025 /
    issue #153) -- substitui `week_over_week`/"vs. última coleta" para
    métricas de PERFIL (Seguidores, % engajamento, NSM): não têm data de
    publicação própria (só um valor observado no momento da coleta), então
    uma comparação "vs. média histórica" é resiliente a qualquer
    espaçamento real entre execuções, ao contrário de "vs. execução
    anterior" (ver docstring do módulo).

    `None` (nunca exceção) se `df_history` estiver vazio, faltar `run_col`,
    ou houver menos de 2 execuções no histórico total -- mesmo critério de
    `week_over_week`, a tela deve ocultar a seta de variação nesse caso.

    Por chave, `delta_percentual=None` (nunca uma média fabricada de 1 valor
    só) se a chave não tiver nenhuma execução ANTERIOR à mais recente, ou se
    a média histórica for nula/zero (divisão por zero)."""
    if df_history.empty or run_col not in df_history.columns:
        return None
    runs = sorted(df_history[run_col].unique())
    if len(runs) < 2:
        return None
    atual_id = runs[-1]

    serie_atual = (
        df_history[df_history[run_col] == atual_id]
        .drop_duplicates(subset=[key_col], keep="last")
        .set_index(key_col)[value_col]
    )
    historico_anterior = df_history[df_history[run_col] != atual_id]

    resultado: dict[object, tuple[object, float | None]] = {}
    for chave, valor_atual in serie_atual.items():
        valores_anteriores = historico_anterior.loc[
            historico_anterior[key_col] == chave, value_col
        ].dropna()
        if valores_anteriores.empty:
            resultado[chave] = (valor_atual, None)
            continue
        media_historica = valores_anteriores.mean()
        if pd.isna(media_historica) or media_historica == 0:
            resultado[chave] = (valor_atual, None)
            continue
        delta_percentual = (valor_atual - media_historica) / media_historica * 100
        resultado[chave] = (valor_atual, delta_percentual)
    return resultado


def deduplicate_by_first_seen(
    df_history: pd.DataFrame,
    id_col: str = "id_comment",
    run_col: str = "_run_id",
) -> pd.DataFrame:
    """Mantém só a linha de menor `run_col` por `id_col` -- a primeira vez que o
    registro foi coletado (ADR 0023). `governor_sentiment_history` é gravado em
    modo append a cada execução; o mesmo comentário pode ser recoletado (e
    reaparecer) numa execução futura se ela voltar a puxar posts já vistos
    antes. Sem esta deduplicação, agregar por data de publicação em vez de por
    `run_col` contaria esse comentário mais de uma vez.

    Retorna `df_history` inalterado se `id_col`/`run_col` estiverem ausentes --
    nunca lança exceção."""
    if df_history.empty or id_col not in df_history.columns or run_col not in df_history.columns:
        return df_history
    return df_history.sort_values(run_col).drop_duplicates(subset=[id_col], keep="first")


def parse_publication_dates(
    df: pd.DataFrame, timestamp_col: str = "timestamp"
) -> pd.Series:
    """`timestamp_col` (string ISO 8601, ex.: `governor_sentiment*.timestamp`)
    parseado para `datetime.date` (ADR 0023) -- mesma lógica de
    `src/features/silver/post_cleaner.py::_parse_timestamp`, reaproveitada
    aqui e em `dashboard/screens/resumo.py` para não duplicar o parse em cada
    lugar que precisa da data real de publicação. Valores não parseáveis
    viram `NaT`, nunca lançam exceção. Série vazia se `timestamp_col` estiver
    ausente."""
    if timestamp_col not in df.columns:
        return pd.Series(dtype="object")
    return pd.to_datetime(df[timestamp_col], errors="coerce", utc=True, format="ISO8601").dt.date


def filter_by_date_range(
    df: pd.DataFrame,
    date_col: str,
    data_inicio: object | None,
    data_fim: object | None,
) -> pd.DataFrame:
    """Restringe `df` ao intervalo `[data_inicio, data_fim]` em `date_col`,
    inclusive (ADR 0023) -- compartilhada entre a linha do tempo do Radar
    (filtra o `DataFrame` já agregado por dia) e o destaque de sentimento do
    Resumo (filtra linhas de comentário individuais antes de agregar por
    tópico). `None` em qualquer lado não corta aquele lado. `DataFrame`
    vazio permanece vazio, nunca lança exceção."""
    if df.empty:
        return df
    filtrado = df
    if data_inicio is not None:
        filtrado = filtrado[filtrado[date_col] >= data_inicio]
    if data_fim is not None:
        filtrado = filtrado[filtrado[date_col] <= data_fim]
    return filtrado.reset_index(drop=True)


def normalize_date_input_range(intervalo: tuple) -> tuple[object, object]:
    """Normaliza o retorno de `st.date_input(..., value=(min, max))` (ADR
    0023) -- o Streamlit devolve uma tupla de 1 elemento enquanto a analista
    ainda não escolheu a segunda data do intervalo; esta função sempre
    devolve `(data_inicio, data_fim)`, usando a mesma data nos dois lados
    nesse caso intermediário. Compartilhada entre `dashboard/screens/radar.py`
    e `dashboard/screens/resumo.py`, que têm o mesmo widget."""
    if len(intervalo) == 2:
        return intervalo[0], intervalo[1]
    return intervalo[0], intervalo[0]


def aggregate_pct_negative_by_publication_day(
    df_history: pd.DataFrame,
    timestamp_col: str = "timestamp",
    sentiment_col: str = "sentiment_label",
    id_col: str = "id_comment",
    run_col: str = "_run_id",
) -> pd.DataFrame:
    """1 linha por dia de publicação (não execução -- ADR 0023): `% negativo =
    count(sentiment_label == 'negative') / count(*)`, já deduplicado por
    `id_col`/menor `run_col` (ver `deduplicate_by_first_seen`) para não contar
    duas vezes um comentário recoletado em execuções sobrepostas.

    `timestamp_col` é parseado via `parse_publication_dates`; linhas com data
    não parseável (`NaT`) são excluídas do resultado, nunca levantam
    exceção. `DataFrame` vazio (colunas `data`/`pct_negativo`, nunca
    exceção) se faltar coluna obrigatória ou não houver linha válida."""
    colunas = ["data", "pct_negativo"]
    required = {timestamp_col, sentiment_col, id_col, run_col}
    if df_history.empty or not required.issubset(df_history.columns):
        return pd.DataFrame(columns=colunas)

    df = deduplicate_by_first_seen(df_history, id_col=id_col, run_col=run_col)
    df = df.assign(data=parse_publication_dates(df, timestamp_col=timestamp_col)).dropna(
        subset=["data"]
    )
    if df.empty:
        return pd.DataFrame(columns=colunas)

    agregado = (
        df.groupby("data")[sentiment_col]
        .apply(lambda s: (s == "negative").mean())
        .rename("pct_negativo")
        .reset_index()
        .sort_values("data")
        .reset_index(drop=True)
    )
    return agregado[colunas]


GAP_DIAS_QUEBRA_LINHA = 7
"""Gap (em dias) acima do qual uma linha de série temporal por data de
publicação quebra visualmente em vez de conectar dois pontos distantes (ADR
0023) -- compartilhado entre `dashboard/screens/radar.py` (linha do tempo de
negatividade) e a seção de evidência de desempenho de
`dashboard/screens/produzir.py` (ADR 0024)."""


def quebrar_em_segmentos(
    df_timeline: pd.DataFrame, gap_dias: int = GAP_DIAS_QUEBRA_LINHA
) -> list[pd.DataFrame]:
    """Divide `df_timeline` (coluna `data`, ordenado por dia de publicação)
    numa lista de segmentos contínuos -- um novo segmento sempre que o
    intervalo entre duas datas consecutivas com dado ultrapassar `gap_dias`
    (ADR 0023). Uma linha contínua ligando dois pontos distantes sugeriria
    uma tendência que o dado real não sustenta, já que não há nenhum dado no
    meio do intervalo.

    Extraída de `dashboard/screens/radar.py` para cá (ADR 0024) quando a
    seção de evidência de desempenho de `dashboard/screens/produzir.py`
    virou um segundo consumidor real -- indiferente ao nome da segunda
    coluna (`pct_negativo`, `valor`, etc.), só olha pra `data`.

    Lista vazia se `df_timeline` estiver vazio."""
    if df_timeline.empty:
        return []
    df = df_timeline.sort_values("data").reset_index(drop=True)
    segmentos: list[pd.DataFrame] = []
    inicio = 0
    for i in range(1, len(df)):
        gap = (df["data"].iloc[i] - df["data"].iloc[i - 1]).days
        if gap > gap_dias:
            segmentos.append(df.iloc[inicio:i].reset_index(drop=True))
            inicio = i
    segmentos.append(df.iloc[inicio:].reset_index(drop=True))
    return segmentos


def aggregate_metric_by_publication_day(
    df: pd.DataFrame,
    metric_col: str | None,
    timestamp_col: str = "data_hora",
    agg: str = "sum",
) -> pd.DataFrame:
    """1 linha por dia de publicação (colunas `data`/`valor`) -- generaliza
    `aggregate_pct_negative_by_publication_day` (ADR 0023) para qualquer
    métrica de post/reel (curtidas, comentários, visualizações, quantidade
    de publicações -- ADR 0024).

    Dois modos de agregação por dia:
    - `agg="sum"` (default): soma de `metric_col` no dia (curtidas,
      comentários, visualizações).
    - `agg="count"`: contagem de linhas no dia, ignora `metric_col` (pode
      ser `None`) -- quantidade de publicações.

    `timestamp_col` default `data_hora` -- já é `datetime` real na Silver
    (`reels_clean`/`posts_clean`), diferente do `timestamp` string ISO de
    `governor_sentiment*` que `parse_publication_dates` trata; por isso o
    parse aqui é direto (`pd.to_datetime`), sem o `format="ISO8601"`/`utc`
    específico daquela função.

    `DataFrame` vazio (colunas `data`/`valor`, nunca exceção) se faltar
    coluna obrigatória ou não houver linha com data parseável."""
    colunas = ["data", "valor"]
    required = {timestamp_col} | (set() if agg == "count" else {metric_col})
    if df.empty or not required.issubset(df.columns):
        return pd.DataFrame(columns=colunas)

    dias = pd.to_datetime(df[timestamp_col], errors="coerce").dt.date
    df = df.assign(_dia=dias).dropna(subset=["_dia"])
    if df.empty:
        return pd.DataFrame(columns=colunas)

    if agg == "count":
        agregado = df.groupby("_dia").size().rename("valor").reset_index()
    else:
        agregado = df.groupby("_dia")[metric_col].sum().rename("valor").reset_index()

    return (
        agregado.rename(columns={"_dia": "data"})
        .sort_values("data")
        .reset_index(drop=True)[colunas]
    )


def run_dates(
    df_history: pd.DataFrame,
    run_col: str = "_run_id",
    timestamp_col: str = "_generated_at",
) -> tuple[object, object] | None:
    """Datas reais (não os `_run_id`s) das 2 execuções mais recentes de
    `df_history`, na ordem `(anterior, atual)` -- para a tela exibir
    "vs. coleta de DD/MM" em vez de "vs. semana anterior" (ver ADR 0021,
    ponto de atrito 4). Retorna `None` se houver menos de 2 execuções."""
    if df_history.empty or run_col not in df_history.columns:
        return None

    runs = sorted(df_history[run_col].unique())
    if len(runs) < 2:
        return None
    atual_id, anterior_id = runs[-1], runs[-2]

    data_atual = df_history.loc[df_history[run_col] == atual_id, timestamp_col].iloc[0]
    data_anterior = df_history.loc[df_history[run_col] == anterior_id, timestamp_col].iloc[0]
    return data_anterior, data_atual
