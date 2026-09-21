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

import pandas as pd

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
